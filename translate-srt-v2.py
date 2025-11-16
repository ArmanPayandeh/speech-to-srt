#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Professional SRT Subtitle Translator using Groq API
Author: SRT Translation Tool
Version: 2.0.0 - Optimized for Groq API with Llama 3.3 70B
"""

import re
import time
import json
from typing import List, Optional, Dict
from dataclasses import dataclass
from pathlib import Path
import logging
import argparse

try:
    from groq import Groq
except ImportError:
    print("❌ خطا: کتابخانه Groq نصب نیست. لطفاً ابتدا آن را نصب کنید:")
    print("   pip install groq")
    exit(1)

# تنظیمات لاگینگ
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
    """کلاس داده برای نگهداری اطلاعات هر بلوک زیرنویس"""
    index: int
    start_time: str
    end_time: str
    text: str
    translated_text: Optional[str] = None


class SRTParser:
    """کلاس پارس و نوشتن فایل‌های SRT"""
    
    @staticmethod
    def parse_srt(file_path: str) -> List[SubtitleBlock]:
        """پارس کردن فایل SRT و استخراج بلوک‌های زیرنویس"""
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as file:
                content = file.read()
        except FileNotFoundError:
            logger.error(f"فایل {file_path} پیدا نشد")
            return []
        except Exception as e:
            logger.error(f"خطا در خواندن فایل: {e}")
            return []

        # نرمال‌سازی خطوط جدید
        content = content.replace('\r\n', '\n').replace('\r', '\n')

        # الگوی regex برای شناسایی بلوک‌های زیرنویس
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

            if text:  # فقط بلوک‌های دارای متن
                subtitles.append(SubtitleBlock(
                    index=index,
                    start_time=start_time,
                    end_time=end_time,
                    text=text
                ))

        logger.info(f"✅ تعداد {len(subtitles)} بلوک زیرنویس پارس شد")

        if len(subtitles) < 5:
            logger.warning(
                "⚠️ تعداد بلوک‌ها غیرعادی کم است؛ احتمالاً فرمت SRT نیاز به بررسی دارد."
            )

        return subtitles

    @staticmethod
    def write_srt(subtitles: List[SubtitleBlock], output_path: str):
        """نوشتن بلوک‌های زیرنویس به فایل SRT"""
        subtitles_sorted = sorted(subtitles, key=lambda s: s.index)

        try:
            with open(output_path, 'w', encoding='utf-8') as file:
                for subtitle in subtitles_sorted:
                    file.write(f"{subtitle.index}\n")
                    file.write(f"{subtitle.start_time} --> {subtitle.end_time}\n")
                    file.write(f"{(subtitle.translated_text or subtitle.text).strip()}\n\n")

            logger.info(f"✅ فایل ترجمه شده در {output_path} ذخیره شد")
        except Exception as e:
            logger.error(f"❌ خطا در نوشتن فایل: {e}")


class GroqTranslator:
    """کلاس ترجمه با استفاده از Groq API"""

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        """
        مقداردهی اولیه مترجم Groq
        
        Args:
            api_key: کلید API Groq
            model: نام مدل (پیش‌فرض: llama-3.3-70b-versatile)
        """
        self.client = Groq(api_key=api_key)
        self.model = model
        
        # دیکشنری اصطلاحات و تگ‌های صوتی رایج نروژی
        self.sound_tags = {
            "[musikk]": "[موسیقی]",
            "[latter]": "[خنده]",
            "[applaus]": "[تشویق]",
            "[hosting]": "[سرفه]",
            "[sukking]": "[آه کشیدن]",
            "[gråt]": "[گریه]",
            "[hvisking]": "[زمزمه]",
            "[skriking]": "[جیغ]",
            "[klapping]": "[کف زدن]",
        }
        
        logger.info(f"✅ GroqTranslator با مدل {model} راه‌اندازی شد")

    def create_system_prompt(self) -> str:
        """ساخت پرامپت سیستمی بهینه برای ترجمه"""
        return """شما یک مترجم حرفه‌ای و متخصص در ترجمه زیرنویس فیلم از نروژی به فارسی هستید.

**تخصص شما:**
• درک عمیق از زبان نروژی و فارسی، شامل اصطلاحات محاوره‌ای، لحن و مفاهیم فرهنگی
• تجربه حرفه‌ای در بومی‌سازی زیرنویس با تاکید بر محدودیت‌های زمانی خواندن
• توانایی انتقال احساسات، لحن و مفاهیم ضمنی با حفظ اختصار
• آگاهی از الگوهای گفتاری محاوره‌ای فارسی و جریان طبیعی دیالوگ

**اصول ترجمه:**
• اولویت با خوانایی و سرعت خواندن بیننده
• حفظ تأثیر احساسی و زمان‌بندی دراماتیک اصلی
• بومی‌سازی ارجاعات فرهنگی برای مخاطبان فارسی‌زبان
• حفظ طنز، کنایه و معانی ظریف
• استفاده از فارسی محاوره‌ای و طبیعی (نه فارسی رسمی و کتابی)

**قوانین مهم:**
• از فارسی محاوره‌ای و روزمره استفاده کنید، نه زبان رسمی
• برای مثال بگویید "میخوام" نه "می‌خواهم"، "نمیدونم" نه "نمی‌دانم"
• هر خط زیرنویس باید حداکثر 35-40 کاراکتر فارسی باشد
• تگ‌های صوتی را ترجمه کنید و داخل براکت نگه دارید
• اسامی خاص را به لاتین بنویسید
• لحن و احساسات گوینده را حفظ کنید"""

    def create_translation_prompt(self, text: str, context: str = "") -> str:
        """
        ساخت پرامپت ترجمه برای یک متن
        
        Args:
            text: متن نروژی برای ترجمه
            context: زمینه از زیرنویس‌های قبلی (اختیاری)
        """
        # جایگزینی تگ‌های صوتی
        processed_text = text
        for nor_tag, per_tag in self.sound_tags.items():
            processed_text = processed_text.replace(nor_tag, per_tag)

        prompt = f"""متن زیرنویس نروژی زیر را به فارسی محاوره‌ای ترجمه کنید:

{f'**زمینه از زیرنویس‌های قبلی:** {context}' if context else ''}

**متن نروژی:**
{processed_text}

**نکات مهم:**
• فقط ترجمه فارسی را بنویسید، بدون توضیح اضافی
• از فارسی محاوره‌ای استفاده کنید (مثال: "میخوام" نه "می‌خواهم")
• تگ‌های صوتی مانند [موسیقی] را حفظ کنید
• اسامی خاص را به لاتین بنویسید
• حداکثر 35-40 کاراکتر فارسی در هر خط
• اگر چند گوینده دارد، تمایز را حفظ کنید

**ترجمه فارسی:**"""

        return prompt

    def create_batch_prompt(self, texts: List[str], context: str = "") -> str:
        """
        ساخت پرامپت برای ترجمه دسته‌ای
        
        Args:
            texts: لیست متون نروژی
            context: زمینه از زیرنویس‌های قبلی
        """
        # پردازش تگ‌های صوتی
        processed_texts = []
        for text in texts:
            for nor_tag, per_tag in self.sound_tags.items():
                text = text.replace(nor_tag, per_tag)
            processed_texts.append(text)

        # ساخت لیست شماره‌دار
        numbered_texts = "\n\n".join([
            f"[{i+1}]\n{text}" 
            for i, text in enumerate(processed_texts)
        ])

        prompt = f"""زیرنویس‌های نروژی زیر را به فارسی محاوره‌ای ترجمه کنید. هر زیرنویس با عدد شماره‌گذاری شده است.

{f'**زمینه کلی:** {context[:200]}' if context else ''}

**زیرنویس‌ها برای ترجمه:**
{numbered_texts}

**قوانین:**
• از فارسی محاوره‌ای و طبیعی استفاده کنید
• ثبات در لحن و اسلوب شخصیت‌ها را حفظ کنید
• تگ‌های صوتی را حفظ کنید
• اسامی خاص را به لاتین بنویسید
• حداکثر 35-40 کاراکتر فارسی در هر خط

**فرمت خروجی (دقیقاً همان شماره‌ها):**
[1] ترجمه فارسی
[2] ترجمه فارسی
[3] ترجمه فارسی
...

فقط ترجمه‌های شماره‌دار را بنویسید، بدون متن اضافی."""

        return prompt

    def _call_api(self, messages: List[Dict], temperature: float = 0.3,
                  max_tokens: int = 2000, timeout: int = 30) -> Optional[str]:
        """
        فراخوانی API Groq
        
        Args:
            messages: لیست پیام‌های گفتگو
            temperature: میزان تصادفی بودن (0-2)
            max_tokens: حداکثر توکن‌های تولیدی
            timeout: زمان timeout
        """
        try:
            chat_completion = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=0.9,
                stream=False,
            )
            
            content = chat_completion.choices[0].message.content
            if content:
                return content.strip()
            return None
            
        except Exception as e:
            logger.error(f"❌ خطا در فراخوانی API: {e}")
            return None

    def translate_text(self, text: str, context: str = "", 
                      retry_count: int = 3) -> str:
        """
        ترجمه یک متن با مدیریت خطا
        
        Args:
            text: متن نروژی
            context: زمینه قبلی
            retry_count: تعداد تلاش مجدد
        """
        prompt = self.create_translation_prompt(text, context)
        
        messages = [
            {"role": "system", "content": self.create_system_prompt()},
            {"role": "user", "content": prompt}
        ]

        for attempt in range(retry_count):
            result = self._call_api(messages, temperature=0.3, max_tokens=500)
            
            if result:
                # پاکسازی ترجمه از متن اضافی
                clean_result = result.strip()
                # حذف عبارات اضافی که ممکن است مدل اضافه کند
                clean_result = re.sub(r'^(ترجمه فارسی:|ترجمه:)\s*', '', clean_result, flags=re.IGNORECASE)
                return clean_result

            if attempt < retry_count - 1:
                wait_time = 2 ** attempt
                logger.warning(f"⏳ تلاش مجدد پس از {wait_time} ثانیه...")
                time.sleep(wait_time)

        logger.error(f"❌ ترجمه ناموفق بعد از {retry_count} تلاش")
        return text

    def translate_batch(self, subtitles: List[SubtitleBlock], 
                       batch_size: int = 5) -> List[SubtitleBlock]:
        """
        ترجمه دسته‌ای زیرنویس‌ها
        
        Args:
            subtitles: لیست بلوک‌های زیرنویس
            batch_size: تعداد زیرنویس در هر دسته
        """
        total = len(subtitles)
        translated_count = 0

        for i in range(0, total, batch_size):
            batch = subtitles[i:i + batch_size]
            batch_texts = [sub.text for sub in batch]

            # ساخت زمینه از زیرنویس‌های قبلی
            context = ""
            if i > 0:
                prev_subtitles = subtitles[max(0, i - 3):i]
                context_parts = []
                for sub in prev_subtitles:
                    if sub.translated_text:
                        context_parts.append(sub.translated_text[:50])
                context = " ← ".join(context_parts)

            # درخواست دسته‌ای
            prompt = self.create_batch_prompt(batch_texts, context)
            messages = [
                {"role": "system", "content": self.create_system_prompt()},
                {"role": "user", "content": prompt}
            ]

            result = self._call_api(messages, temperature=0.3, max_tokens=2000)

            if not result:
                logger.warning("⚠️ ترجمه دسته‌ای ناموفق، استفاده از ترجمه تکی...")
                for sub in batch:
                    sub.translated_text = self.translate_text(sub.text, context)
                    translated_count += 1
                time.sleep(1)
                continue

            # استخراج ترجمه‌ها با regex
            pattern = r'\[(\d+)\]\s*(.*?)(?=\n\s*\[\d+\]|\Z)'
            pairs = re.findall(pattern, result, flags=re.DOTALL)

            translations_applied = False
            for num_str, translation in pairs:
                idx_local = int(num_str) - 1
                if 0 <= idx_local < len(batch):
                    clean_translation = translation.strip()
                    # حذف خطوط اضافی
                    clean_translation = re.sub(r'\n{3,}', '\n\n', clean_translation)
                    
                    batch[idx_local].translated_text = clean_translation
                    translated_count += 1
                    translations_applied = True

            # fallback به ترجمه تکی
            if not translations_applied:
                logger.warning("⚠️ فرمت پاسخ نامعتبر، استفاده از ترجمه تکی...")
                for sub in batch:
                    if not sub.translated_text:
                        sub.translated_text = self.translate_text(sub.text, context)
                        translated_count += 1

            # نمایش پیشرفت
            progress = (translated_count / total) * 100
            logger.info(f"📊 پیشرفت: {translated_count}/{total} ({progress:.1f}%)")
            
            # تاخیر برای جلوگیری از rate limiting
            time.sleep(0.5)

        return subtitles


class SRTTranslationManager:
    """مدیریت کل فرآیند ترجمه"""

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        """
        مقداردهی اولیه مدیر ترجمه
        
        Args:
            api_key: کلید API Groq
            model: نام مدل
        """
        self.parser = SRTParser()
        self.translator = GroqTranslator(api_key, model)
        logger.info(f"🚀 SRTTranslationManager با مدل {model} آماده شد")

    def translate_file(self, input_path: str, output_path: Optional[str] = None,
                      batch_size: int = 5) -> Optional[Path]:
        """
        ترجمه کامل یک فایل SRT
        
        Args:
            input_path: مسیر فایل ورودی
            output_path: مسیر فایل خروجی (اختیاری)
            batch_size: تعداد زیرنویس در هر دسته
        """
        # تعیین مسیر خروجی
        if not output_path:
            input_file = Path(input_path)
            output_path = input_file.parent / f"{input_file.stem}_persian.srt"
        else:
            output_path = Path(output_path)

        logger.info(f"🎬 شروع ترجمه فایل: {input_path}")
        logger.info(f"📝 فایل خروجی: {output_path}")

        # پارس فایل
        subtitles = self.parser.parse_srt(input_path)
        if not subtitles:
            logger.error("❌ هیچ زیرنویسی برای ترجمه یافت نشد")
            return None

        # ترجمه
        start_time = time.time()
        translated_subtitles = self.translator.translate_batch(subtitles, batch_size)

        # ذخیره فایل
        self.parser.write_srt(translated_subtitles, str(output_path))

        # آمار نهایی
        elapsed_time = time.time() - start_time
        success_count = sum(1 for s in translated_subtitles if s.translated_text)
        
        logger.info(f"✅ ترجمه کامل شد در {elapsed_time:.2f} ثانیه")
        logger.info(f"📈 آمار: {success_count}/{len(subtitles)} زیرنویس با موفقیت ترجمه شد")
        
        if success_count < len(subtitles):
            logger.warning(f"⚠️ {len(subtitles) - success_count} زیرنویس ترجمه نشد")

        return output_path


def main():
    """تابع اصلی برنامه"""
    
    # 🔑 کلید API خود را اینجا قرار دهید
    DEFAULT_API_KEY = ""  # کلید API خود را اینجا بگذارید
    
    parser = argparse.ArgumentParser(
        description='🎬 ترجمه حرفه‌ای فایل‌های SRT نروژی به فارسی با Groq API',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
مثال‌های استفاده:
  %(prog)s input.srt
  %(prog)s input.srt -o output.srt
  %(prog)s input.srt -b 10
  %(prog)s input.srt -m llama-3.1-8b-instant
        """
    )
    
    parser.add_argument('input_file', help='مسیر فایل SRT ورودی')
    parser.add_argument('-o', '--output', help='مسیر فایل خروجی (اختیاری)')
    parser.add_argument('-k', '--api-key', default=DEFAULT_API_KEY,
                       help='کلید API Groq (اختیاری - از مقدار پیش‌فرض استفاده می‌شود)')
    parser.add_argument('-m', '--model', default='llama-3.3-70b-versatile',
                       choices=[
                           'llama-3.3-70b-versatile',
                           'llama-3.1-8b-instant',
                           'meta-llama/llama-4-maverick-17b-128e-instruct',
                           'meta-llama/llama-4-scout-17b-16e-instruct'
                       ],
                       help='مدل مورد استفاده (پیش‌فرض: llama-3.3-70b-versatile)')
    parser.add_argument('-b', '--batch-size', type=int, default=5,
                       help='تعداد زیرنویس در هر دسته (پیش‌فرض: 5)')

    args = parser.parse_args()

    # بررسی وجود فایل ورودی
    if not Path(args.input_file).exists():
        print(f"❌ خطا: فایل {args.input_file} پیدا نشد")
        return 1

    print("=" * 60)
    print("🎬 مترجم حرفه‌ای زیرنویس SRT با Groq API")
    print("=" * 60)
    print(f"📥 فایل ورودی: {args.input_file}")
    print(f"🤖 مدل: {args.model}")
    print(f"📦 اندازه دسته: {args.batch_size}")
    print("=" * 60)

    # ایجاد مدیر ترجمه
    manager = SRTTranslationManager(args.api_key, args.model)

    try:
        output_file = manager.translate_file(
            args.input_file,
            args.output,
            args.batch_size
        )
        
        if output_file:
            print("\n" + "=" * 60)
            print("✅ ترجمه با موفقیت انجام شد!")
            print(f"📁 فایل خروجی: {output_file}")
            print("=" * 60)
            return 0
        else:
            print("\n❌ ترجمه ناموفق بود")
            return 1

    except KeyboardInterrupt:
        print("\n⚠️ ترجمه توسط کاربر متوقف شد")
        return 1
    except Exception as e:
        logger.error(f"❌ خطای غیرمنتظره: {str(e)}")
        return 1


if __name__ == "__main__":
    exit(main())
