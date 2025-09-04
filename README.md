1- mp4 to wav
ffmpeg -i 1.mp4 -vn -ac 1 -ar 16000 video.wav

2- wav to str 
https://elevenlabs.io/app/speech-to-text

3- main py
srt translate
 python3 main.py video_no.srt -k  -o output_persian.srt -m google/gemma-3-27b-it:free -b 10

 ffmpeg -i video.mp4 -vf "subtitles=video.srt:force_style='Fontsize=60,BorderStyle=3,BackColour=&H00000000,PrimaryColour=&H00FFFFFF,Outline=0,MarginV=40'" -c:a copy output.mp4
