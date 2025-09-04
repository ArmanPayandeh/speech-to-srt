#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Professional SRT Subtitle Translator using Avalai API
Author: SRT Translation Tool
Version: 1.2.0 - Modified for Avalai API
"""

import re
import time
import json
import requests
from typing import List, Optional, Dict
from dataclasses import dataclass
from pathlib import Path
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed 
import argparse

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('srt_translation.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class SubtitleBlock:
    index: int
    start_time: str
    end_time: str
    text: str
    translated_text: Optional[str] = None


class SRTParser:
    @staticmethod
    def parse_srt(file_path: str) -> List[SubtitleBlock]:
        with open(file_path, 'r', encoding='utf-8-sig') as file:
            content = file.read()

        content = content.replace('\r\n', '\n').replace('\r', '\n')

        pattern = (
            r'(?m)^\s*(\d+)\s*\n'                                  
            r'(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*'              
            r'(\d{2}:\d{2}:\d{2}[,\.]\d{3}).*?\n'                  
            r'([\s\S]*?)'                                         
            r'(?=\n{2,}\d+\s*\n|\Z)'                               
        )

        matches = re.finditer(pattern, content)
        subtitles: List[SubtitleBlock] = []

        for match in matches:
            index = int(match.group(1))
            start_time = match.group(2).replace('.', ',')
            end_time = match.group(3).replace('.', ',')
            text = match.group(4).strip()

            subtitles.append(SubtitleBlock(
                index=index,
                start_time=start_time,
                end_time=end_time,
                text=text
            ))

        logger.info(f"تعداد {len(subtitles)} بلوک زیرنویس پارس شد")

        if len(subtitles) < 5:
            logger.warning(
                "تعداد بلوک‌ها غیرعادی کم است؛ احتمالاً فرمت SRT یا regex نیاز به بررسی دارد."
            )

        return subtitles

    @staticmethod
    def write_srt(subtitles: List[SubtitleBlock], output_path: str):
        """نوشتن بلوک‌های زیرنویس به فایل SRT"""
        subtitles_sorted = sorted(subtitles, key=lambda s: s.index)

        with open(output_path, 'w', encoding='utf-8') as file:
            for subtitle in subtitles_sorted:
                file.write(f"{subtitle.index}\n")
                file.write(f"{subtitle.start_time} --> {subtitle.end_time}\n")
                file.write(f"{(subtitle.translated_text or subtitle.text).strip()}\n\n")

        logger.info(f"فایل ترجمه شده در {output_path} ذخیره شد")


class AvalaiTranslator:
    """کلاس برای ترجمه متون با استفاده از Avalai API"""

    def __init__(self, api_key: str, model: str = "gpt-4"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.avalai.ir/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
        # دیکشنری اصطلاحات رایج نروژی
        self.common_terms = {
            "sound_tags": {
                "[musikk]": "[موسیقی]",
                "[latter]": "[خنده]",
                "[applaus]": "[تشویق]",
                "[hosting]": "[سرفه]",
                "[sukking]": "[آه]",
                "[gråt]": "[گریه]"
            }
        }

    def create_enhanced_system_prompt(self) -> str:
        """ساخت پرامپت سیستمی بهینه‌شده"""
        return """You are an expert subtitle translator specializing in Norwegian to Persian (Farsi) translation for film and TV content.

YOUR EXPERTISE:
• Deep understanding of both Norwegian and Persian languages, including idioms, slang, and cultural references
• Professional experience in subtitle localization with emphasis on timing constraints
• Ability to convey emotion, tone, and subtext while maintaining brevity
• Knowledge of Persian colloquial speech patterns and natural dialogue flow

TRANSLATION PHILOSOPHY:
• Prioritize viewer comprehension and reading speed
• Maintain the original's emotional impact and dramatic timing
• Adapt cultural references when necessary for Persian audiences
• Preserve humor, sarcasm, and subtle meanings"""

    def create_translation_prompt(self, text: str, context: str = "", 
                                 scene_description: str = "") -> str:
        """ساخت پرامپت بهینه برای ترجمه زیرنویس"""
        
        # پیش‌پردازش تگ‌های صدا
        for eng, per in self.common_terms["sound_tags"].items():
            text = text.replace(eng, f"{{SOUND:{per}}}")
        
        prompt = f"""Translate the following Norwegian subtitle to Persian (Farsi).

CRITICAL TRANSLATION RULES:
1. **Natural Flow**: Use conversational Persian that sounds natural when spoken
2. **Reading Speed**: Keep translations concise (max 35-40 characters per line for 1-2 second subtitles)
3. **Cultural Adaptation**: 
   - Adapt idioms to Persian equivalents
   - Keep proper names in Latin script
   - Translate titles/honorifics appropriately (Herr→آقای, Fru→خانم)
4. **Tone Preservation**:
   - Match the formality level (formal تو vs informal شما)
   - Preserve emotional undertones
   - Maintain humor and sarcasm markers
5. **Technical Elements**:
   - {{SOUND:x}} tags should remain as provided
   - Preserve line breaks for dramatic effect
   - Keep punctuation that indicates pauses or emphasis

{f'PREVIOUS CONTEXT (for continuity): {context}' if context else ''}
{f'SCENE INFO: {scene_description}' if scene_description else ''}

NORWEGIAN TEXT:
{text}

IMPORTANT NOTES:
- If text contains dialogue between multiple speakers, maintain clear distinction
- For questions, ensure Persian question markers (آیا، مگر) are used appropriately
- Numbers: Use Persian numerals (۱۲۳) for general text, keep Western (123) for technical terms

OUTPUT: Provide ONLY the Persian translation without any explanation or metadata."""
        
        return prompt

    def create_batch_prompt(self, texts: List[str], context: str = "") -> str:
        """پرامپت بهینه‌شده برای ترجمه دسته‌ای"""
        
        # پیش‌پردازش تگ‌های صدا برای همه متون
        processed_texts = []
        for text in texts:
            for eng, per in self.common_terms["sound_tags"].items():
                text = text.replace(eng, f"{{SOUND:{per}}}")
            processed_texts.append(text)
        
        combined_text = "\n---\n".join([f"[{i+1}] {text}" for i, text in enumerate(processed_texts)])
        
        prompt = f"""Translate these Norwegian subtitles to Persian. Each is numbered and must be translated separately.

TRANSLATION GUIDELINES:
• Use natural, conversational Persian
• Maintain consistency in character speech patterns across subtitles
• Adapt idioms and cultural references appropriately
• Keep proper names in Latin script
• Preserve timing markers and sound tags {{SOUND:x}}
• Maximum 35-40 Persian characters per line for readability

{f'CONTEXT FROM PREVIOUS SUBTITLES: {context[:300]}' if context else ''}

SUBTITLES TO TRANSLATE:
{combined_text}

REQUIRED FORMAT (maintain exact numbering):
[1] Persian translation
[2] Persian translation
[3] Persian translation
...

Provide ONLY the numbered translations without any additional text."""
        
        return prompt

    def _post_chat(self, messages: List[Dict], temperature: float = 0.3, 
                   max_tokens: int = 1000, timeout: int = 45) -> Optional[str]:
        """ارسال درخواست به Avalai API با پرامپت سیستمی"""
        
        # اضافه کردن پرامپت سیستمی
        full_messages = [
            {"role": "system", "content": self.create_enhanced_system_prompt()},
            *messages
        ]
        
        payload = {
            "model": self.model,
            "messages": full_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": 0.9,
            "frequency_penalty": 0.3,
        }
        
        try:
            resp = self.session.post(self.base_url, json=payload, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                content = data.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
                
                # پس‌پردازش: بازگرداندن تگ‌های صدا
                for placeholder, persian in self.common_terms["sound_tags"].items():
                    content = content.replace(f"{{SOUND:{persian}}}", persian)
                
                return content
            elif resp.status_code == 429:
                logger.warning("Rate limit دریافت شد.")
                return None
            else:
                logger.error(f"API Error: {resp.status_code} - {resp.text}")
                return None
        except Exception as e:
            logger.error(f"خطا در ارتباط با API: {e}")
            return None

    def translate_text(self, text: str, context: str = "", 
                      scene_description: str = "", retry_count: int = 3) -> str:
        """ترجمه یک متن با مدیریت خطا و retry"""
        prompt = self.create_translation_prompt(text, context, scene_description)

        for attempt in range(retry_count):
            result = self._post_chat(
                [{"role": "user", "content": prompt}], 
                temperature=0.3, 
                max_tokens=1000, 
                timeout=45
            )
            if result:
                return result

            wait_time = 2 ** attempt
            logger.warning(f"تلاش مجدد ترجمه تکی پس از {wait_time} ثانیه ...")
            time.sleep(wait_time)

        return text

    def translate_batch(self, subtitles: List[SubtitleBlock], batch_size: int = 5) -> List[SubtitleBlock]:
        """ترجمه دسته‌ای زیرنویس‌ها با پرامپت بهینه‌شده"""
        total = len(subtitles)
        translated_count = 0

        for i in range(0, total, batch_size):
            batch = subtitles[i:i + batch_size]
            
            # استخراج متون دسته
            batch_texts = [sub.text for sub in batch]

            # Context از زیرنویس‌های قبلی
            context = ""
            if i > 0:
                prev_subtitles = subtitles[max(0, i - 5):i]
                context_parts = []
                for sub in prev_subtitles[-3:]:
                    if sub.translated_text:
                        context_parts.append(f"[{sub.translated_text}]")
                context = " ← ".join(context_parts)

            # درخواست دسته‌ای با پرامپت بهینه‌شده
            prompt = self.create_batch_prompt(batch_texts, context)
            result = self._post_chat(
                [{"role": "user", "content": prompt}], 
                temperature=0.3, 
                max_tokens=2000, 
                timeout=60
            )

            if not result:
                logger.error("ترجمهٔ دسته‌ای ناموفق؛ سوییچ به ترجمهٔ تکی.")
                for sub in batch:
                    sub.translated_text = self.translate_text(sub.text, context)
                    translated_count += 1
                time.sleep(1)
                continue

            # استخراج ترجمه‌ها با regex قوی‌تر
            pattern = r'\[(\d+)\]\s*(.*?)(?=\n\s*\[\d+\]|\Z)'
            pairs = re.findall(pattern, result, flags=re.DOTALL)

            translations_applied = False
            for num_str, translation in pairs:
                idx_local = int(num_str) - 1
                if 0 <= idx_local < len(batch):
                    # پاکسازی ترجمه
                    clean_translation = translation.strip()
                    # حذف خطوط اضافی
                    clean_translation = re.sub(r'\n{3,}', '\n\n', clean_translation)
                    
                    batch[idx_local].translated_text = clean_translation
                    translated_count += 1
                    translations_applied = True

            if not translations_applied:
                logger.warning("فرمت پاسخ نامنتظر؛ fallback به ترجمه تکی.")
                for sub in batch:
                    if not sub.translated_text:
                        sub.translated_text = self.translate_text(sub.text, context)
                        translated_count += 1

            logger.info(f"پیشرفت: {translated_count}/{total} زیرنویس ترجمه شد")
            
            # تاخیر دینامیک بر اساس API
            time.sleep(0.8)

        return subtitles


class SRTTranslationManager:
    """مدیریت کل فرآیند ترجمه"""

    def __init__(self, api_key: str, model: str = "gpt-4"):
        self.parser = SRTParser()
        self.translator = AvalaiTranslator(api_key, model)

    def translate_file(self, input_path: str, output_path: Optional[str] = None, 
                      batch_size: int = 5):
        """ترجمه کامل یک فایل SRT"""
        if not output_path:
            input_file = Path(input_path)
            output_path = input_file.parent / f"{input_file.stem}_persian.srt"
        else:
            output_path = Path(output_path)

        logger.info(f"شروع ترجمه فایل: {input_path}")

        subtitles = self.parser.parse_srt(input_path)

        if not subtitles:
            logger.error("هیچ زیرنویسی برای ترجمه یافت نشد")
            return

        start_time = time.time()
        translated_subtitles = self.translator.translate_batch(subtitles, batch_size)

        self.parser.write_srt(translated_subtitles, str(output_path))

        elapsed_time = time.time() - start_time
        logger.info(f"ترجمه کامل شد در {elapsed_time:.2f} ثانیه")

        success_count = sum(1 for s in translated_subtitles if s.translated_text)
        logger.info(f"آمار: {success_count}/{len(subtitles)} زیرنویس با موفقیت ترجمه شد")

        return output_path


def main():
    """تابع اصلی برنامه"""
    parser = argparse.ArgumentParser(description='ترجمه حرفه‌ای فایل‌های SRT با Avalai API')
    parser.add_argument('input_file', help='مسیر فایل SRT ورودی')
    parser.add_argument('-o', '--output', help='مسیر فایل خروجی (اختیاری)')
    parser.add_argument('-k', '--api-key', required=True, help='کلید API Avalai')
    parser.add_argument('-m', '--model', default='gpt-4',
                        help='مدل مورد استفاده (پیش‌فرض: gpt-4)')
    parser.add_argument('-b', '--batch-size', type=int, default=5,
                        help='تعداد زیرنویس در هر دسته (پیش‌فرض: 5)')

    args = parser.parse_args()

    manager = SRTTranslationManager(args.api_key, args.model)

    try:
        output_file = manager.translate_file(
            args.input_file,
            args.output,
            args.batch_size
        )
        print("\n✅ ترجمه با موفقیت انجام شد!")
        print(f"📁 فایل خروجی: {output_file}")

    except Exception as e:
        logger.error(f"خطا در ترجمه: {str(e)}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
