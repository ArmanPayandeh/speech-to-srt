import os
import sys
import html
from pathlib import Path
from typing import Optional, Dict
from groq import Groq


class AudioToSRTConverter:
    """تبدیل فایل‌های صوتی به زیرنویس SRT با استفاده از Groq API"""
    
    def __init__(self, api_key: str):
        """
        مقداردهی اولیه converter
        
        Args:
            api_key: کلید API از Groq
        """
        self.client = Groq(api_key=api_key)
        
        # نقشه تصحیح کاراکترهای نروژی و سایر زبان‌ها
        self.char_replacements = {
            'Ã¥': 'å', 'Ã¦': 'æ', 'Ã¸': 'ø',
            'Ã…': 'Å', 'Ã†': 'Æ', 'Ã˜': 'Ø',
            'nÃ¥': 'nå', 'pÃ¥': 'på', 'sÃ¥': 'så',
            'mÃ¥': 'må', 'gÃ¥': 'gå', 'fÃ¸': 'fø',
            'gjÃ¸': 'gjø', 'hÃ¸': 'hø', 'skjÃ¸': 'skjø',
            'Ã¸de': 'øde'
        }
    
    @staticmethod
    def clean_text(text: str, replacements: Dict[str, str]) -> str:
        """
        تمیزسازی و اصلاح متن
        
        Args:
            text: متن ورودی
            replacements: دیکشنری جایگزینی کاراکترها
            
        Returns:
            متن تمیز شده
        """
        # تبدیل HTML entities
        text = html.unescape(text)
        
        # اعمال جایگزینی‌های کاراکتر
        for old, new in replacements.items():
            text = text.replace(old, new)
        
        return text.strip()
    
    @staticmethod
    def seconds_to_srt_time(seconds: float) -> str:
        """
        تبدیل ثانیه به فرمت زمان SRT (HH:MM:SS,mmm)
        
        Args:
            seconds: زمان به ثانیه
            
        Returns:
            رشته زمان به فرمت SRT
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millisecs = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"
    
    def transcribe_audio(
        self,
        audio_path: str,
        language: str = "no",
        model: str = "whisper-large-v3-turbo",
        prompt: Optional[str] = None,
        temperature: float = 0.0
    ) -> Dict:
        """
        تبدیل فایل صوتی به متن با استفاده از Groq API
        
        Args:
            audio_path: مسیر فایل صوتی
            language: کد زبان (ISO-639-1)
            model: مدل Whisper (whisper-large-v3-turbo یا whisper-large-v3)
            prompt: راهنمای اختیاری برای مدل
            temperature: دمای مدل (0-1)
            
        Returns:
            نتیجه transcription شامل segments و metadata
        """
        # بررسی وجود فایل
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"❌ فایل صوتی پیدا نشد: {audio_path}")
        
        # بررسی سایز فایل (محدودیت 25MB برای free tier)
        file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
        print(f"📁 سایز فایل: {file_size_mb:.2f} MB")
        
        if file_size_mb > 25:
            print(f"⚠️  هشدار: سایز فایل بیشتر از 25MB است.")
            print("   توصیه می‌شود فایل را به فرمت FLAC تبدیل کنید.")
        
        print(f"🎙️  در حال transcribe کردن {Path(audio_path).name}...")
        print(f"   مدل: {model}")
        print(f"   زبان: {language}")
        
        # خواندن فایل و ارسال به صورت tuple (برای رفع مشکل Content-Length)
        filename = Path(audio_path).name
        with open(audio_path, "rb") as audio_file:
            audio_data = audio_file.read()
        
        transcription = self.client.audio.transcriptions.create(
            file=(filename, audio_data),
            model=model,
            response_format="verbose_json",
            language=language,
            prompt=prompt,
            temperature=temperature,
            timestamp_granularities=["segment"]
        )
        
        return transcription
    
    def generate_srt(
        self,
        transcription: Dict,
        output_path: str,
        clean_chars: bool = True
    ) -> None:
        """
        تولید فایل SRT از نتیجه transcription
        
        Args:
            transcription: نتیجه transcription از Groq
            output_path: مسیر فایل خروجی SRT
            clean_chars: فعال‌سازی تمیزسازی کاراکترها
        """
        srt_content = []
        segment_number = 1
        
        for segment in transcription.segments:
            start_time = segment["start"]
            end_time = segment["end"]
            text = segment["text"]
            
            # تمیزسازی متن در صورت نیاز
            if clean_chars:
                text = self.clean_text(text, self.char_replacements)
            
            # ساخت فرمت SRT
            srt_content.append(str(segment_number))
            srt_content.append(
                f"{self.seconds_to_srt_time(start_time)} --> "
                f"{self.seconds_to_srt_time(end_time)}"
            )
            srt_content.append(text)
            srt_content.append("")  # خط خالی بین segments
            
            segment_number += 1
        
        # نوشتن فایل SRT
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(srt_content))
        
        print(f"✅ فایل SRT ایجاد شد: {output_path}")
    
    def analyze_transcription_quality(self, transcription: Dict) -> None:
        """
        تحلیل کیفیت transcription بر اساس metadata
        
        Args:
            transcription: نتیجه transcription از Groq
        """
        print("\n📊 تحلیل کیفیت:")
        print(f"   تعداد segments: {len(transcription.segments)}")
        print(f"   مدت زمان کل: {transcription.duration:.1f} ثانیه")
        
        # تحلیل segments با کیفیت پایین
        low_confidence_segments = []
        high_no_speech_segments = []
        
        for i, segment in enumerate(transcription.segments):
            avg_logprob = segment.get("avg_logprob", 0)
            no_speech_prob = segment.get("no_speech_prob", 0)
            
            # شناسایی segments مشکوک
            if avg_logprob < -0.5:
                low_confidence_segments.append((i, avg_logprob))
            
            if no_speech_prob > 0.5:
                high_no_speech_segments.append((i, no_speech_prob))
        
        if low_confidence_segments:
            print(f"\n⚠️  {len(low_confidence_segments)} segment با اطمینان پایین:")
            for idx, prob in low_confidence_segments[:3]:  # نمایش 3 مورد اول
                print(f"   Segment {idx}: avg_logprob = {prob:.3f}")
        
        if high_no_speech_segments:
            print(f"\n⚠️  {len(high_no_speech_segments)} segment با احتمال no-speech بالا:")
            for idx, prob in high_no_speech_segments[:3]:
                print(f"   Segment {idx}: no_speech_prob = {prob:.3f}")
        
        if not low_confidence_segments and not high_no_speech_segments:
            print("   ✓ کیفیت transcription عالی است!")
    
    def convert(
        self,
        audio_path: str,
        output_path: Optional[str] = None,
        language: str = "no",
        model: str = "whisper-large-v3-turbo",
        analyze_quality: bool = True
    ) -> None:
        """
        تبدیل کامل فایل صوتی به SRT
        
        Args:
            audio_path: مسیر فایل صوتی
            output_path: مسیر فایل خروجی (اختیاری)
            language: کد زبان
            model: مدل Whisper
            analyze_quality: نمایش تحلیل کیفیت
        """
        # تعیین مسیر خروجی
        if output_path is None:
            output_path = Path(audio_path).stem + ".srt"
        
        # Transcription
        transcription = self.transcribe_audio(
            audio_path=audio_path,
            language=language,
            model=model
        )
        
        # تولید SRT
        self.generate_srt(transcription, output_path)
        
        # تحلیل کیفیت
        if analyze_quality:
            self.analyze_transcription_quality(transcription)


def print_usage():
    """نمایش راهنمای استفاده"""
    print("=" * 60)
    print("🎬 تبدیل فایل صوتی به زیرنویس SRT با Groq API")
    print("=" * 60)
    print("\n📖 نحوه استفاده:")
    print("   python3 a.py <آدرس_فایل_صوتی> <نام_فایل_خروجی>")
    print("\n💡 مثال:")
    print("   python3 a.py audio.flac output.srt")
    print("   python3 a.py /path/to/video.mp4 subtitle")
    print("\n📝 توجه:")
    print("   - اگر نام خروجی را وارد نکنید، از نام فایل ورودی استفاده می‌شود")
    print("   - پسوند .srt به صورت خودکار اضافه می‌شود")
    print("\n🌍 فرمت‌های پشتیبانی شده:")
    print("   flac, mp3, mp4, wav, webm, m4a, ogg, mpeg, mpga")
    print("=" * 60)


def main():
    """تابع اصلی برای استفاده از converter با آرگومان‌های خط فرمان"""
    
    # بررسی آرگومان‌ها
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)
    
    # گرفتن آرگومان‌ها
    audio_file = sys.argv[1]
    
    # تعیین نام فایل خروجی
    if len(sys.argv) >= 3:
        output_file = sys.argv[2]
        # اضافه کردن پسوند .srt اگر وجود نداشته باشد
        if not output_file.endswith('.srt'):
            output_file += '.srt'
    else:
        # استفاده از نام فایل ورودی
        output_file = Path(audio_file).stem + ".srt"
    
    # تنظیمات - API KEY را اینجا وارد کنید
    API_KEY = ""
    
    if API_KEY == "your_groq_api_key_here":
        print("❌ خطا: API Key تنظیم نشده است!")
        print("\n💡 راه‌های تنظیم API Key:")
        print("   1. متغیر محیطی: export GROQ_API_KEY='your_key'")
        print("   2. مستقیماً در کد: API_KEY = 'your_key'")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("🚀 شروع پردازش...")
    print("=" * 60)
    print(f"📂 فایل ورودی: {audio_file}")
    print(f"💾 فایل خروجی: {output_file}")
    print("=" * 60 + "\n")
    
    try:
        # ایجاد converter
        converter = AudioToSRTConverter(api_key=API_KEY)
        
        # تبدیل فایل
        converter.convert(
            audio_path=audio_file,
            output_path=output_file,
            language="no",  # می‌توانید این را تغییر دهید: en, fa, ar, ...
            model="whisper-large-v3",  # یا whisper-large-v3 برای دقت بیشتر
            analyze_quality=True
        )
        
        print("\n" + "=" * 60)
        print("🎉 پردازش با موفقیت انجام شد!")
        print("=" * 60)
        
    except FileNotFoundError as e:
        print(f"\n❌ خطا: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ خطای غیرمنتظره: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
