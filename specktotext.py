from openai import OpenAI
import html

def clean_text(text):
    """تمیز کردن متن از کاراکترهای مشکل‌دار"""
    # تبدیل HTML entities
    text = html.unescape(text)
    
    # تصحیح کاراکترهای نروژی
    replacements = {
        'Ã¥': 'å',
        'Ã¦': 'æ', 
        'Ã¸': 'ø',
        'Ã…': 'Å',
        'Ã†': 'Æ',
        'Ã˜': 'Ø',
        'nÃ¥': 'nå',
        'pÃ¥': 'på',
        'sÃ¥': 'så',
        'mÃ¥': 'må',
        'gÃ¥': 'gå',
        'fÃ¸': 'fø',
        'gjÃ¸': 'gjø',
        'hÃ¸': 'hø',
        'skjÃ¸': 'skjø',
        'Ã¸de': 'øde'
    }
    
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    return text.strip()

def seconds_to_srt_time(seconds):
    """تبدیل ثانیه به فرمت زمان SRT"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millisecs = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"

# تنظیم client
client = OpenAI(
    api_key="",
    base_url="https://api.avalai.ir/v1"
)

# باز کردن فایل صوتی
with open("Rykter.wav", "rb") as audio_file:
    # گرفتن خروجی JSON برای دسترسی به segments
    transcript = client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
        response_format="verbose_json",
        language="no"
    )

# ایجاد فایل SRT تمیز
srt_content = []
segment_number = 1

for segment in transcript.segments:
    start_time = segment.start
    end_time = segment.end
    text = clean_text(segment.text)
    
    # ساخت فرمت SRT
    srt_content.append(str(segment_number))
    srt_content.append(f"{seconds_to_srt_time(start_time)} --> {seconds_to_srt_time(end_time)}")
    srt_content.append(text)
    srt_content.append("")  # خط خالی
    
    segment_number += 1

# نوشتن فایل SRT تمیز
with open("1.srt", "w", encoding="utf-8") as f:
    f.write("\n".join(srt_content))

print("فایل 1.srt با فرمت استاندارد و کاراکترهای تمیز ایجاد شد!")
print(f"تعداد segments: {len(transcript.segments)}")
print(f"مدت زمان کل: {transcript.duration:.1f} ثانیه")