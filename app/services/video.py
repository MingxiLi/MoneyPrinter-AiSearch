import glob
import random
from typing import List
from PIL import ImageFont
from loguru import logger
from moviepy.editor import *
from moviepy.video.tools.subtitles import SubtitlesClip

from app.models.schema import VideoAspect, VideoParams, VideoConcatMode
from app.utils import utils


def get_bgm_file(bgm_type: str = "random", bgm_file: str = ""):
    if not bgm_type:
        return ""

    if bgm_file and os.path.exists(bgm_file):
        return bgm_file

    if bgm_type == "random":
        suffix = "*.mp3"
        song_dir = utils.song_dir()
        files = glob.glob(os.path.join(song_dir, suffix))
        return random.choice(files)

    return ""


def combine_videos(combined_video_path: str,
                   video_paths: List[str],
                   audio_duration: float,
                   video_aspect: VideoAspect = VideoAspect.portrait,
                   threads: int = 2,
                   ) -> str:
    output_dir = os.path.dirname(combined_video_path)

    aspect = VideoAspect(video_aspect)
    video_width, video_height = aspect.to_resolution()

    clips = []
    video_duration = 0
    # Add downloaded clips over and over until the duration of the audio (max_duration) has been reached
    for video_path in video_paths:
        clip = VideoFileClip(video_path).without_audio()
        clip = clip.set_fps(30)

        # Not all videos are same size, so we need to resize them
        clip_w, clip_h = clip.size
        if clip_w != video_width or clip_h != video_height:
            clip_ratio = clip.w / clip.h
            video_ratio = video_width / video_height

            if clip_ratio == video_ratio:
                # 等比例缩放
                clip = clip.resize((video_width, video_height))
            else:
                # 等比缩放视频
                if clip_ratio > video_ratio:
                    # 按照目标宽度等比缩放
                    scale_factor = video_width / clip_w
                else:
                    # 按照目标高度等比缩放
                    scale_factor = video_height / clip_h

                new_width = int(clip_w * scale_factor)
                new_height = int(clip_h * scale_factor)
                clip_resized = clip.resize(newsize=(new_width, new_height))

                background = ColorClip(size=(video_width, video_height), color=(0, 0, 0))
                clip = CompositeVideoClip([
                    background.set_duration(clip.duration),
                    clip_resized.set_position("center")
                ])

            logger.info(f"resizing video to {video_width} x {video_height}, clip size: {clip_w} x {clip_h}")

        clips.append(clip)
        video_duration += clip.duration
        logger.info(f"video_duration {video_duration, audio_duration}")

    final_clip = concatenate_videoclips(clips)
    final_clip = final_clip.set_fps(30)
    logger.info(f"writing")
    final_clip.write_videofile(filename=combined_video_path,
                               threads=threads,
                               logger=None,
                               temp_audiofile_path=output_dir,
                               audio_codec="aac",
                               fps=30,
                               )
    logger.success(f"completed")
    return combined_video_path


def wrap_text(text, max_width, font='Arial', fontsize=60):
    # 创建字体对象
    font = ImageFont.truetype(font, fontsize)

    def get_text_size(inner_text):
        inner_text = inner_text.strip()
        left, top, right, bottom = font.getbbox(inner_text)
        return right - left, bottom - top

    width, height = get_text_size(text)
    if width <= max_width:
        return text, height

    # logger.warning(f"wrapping text, max_width: {max_width}, text_width: {width}, text: {text}")

    processed = True

    _wrapped_lines_ = []
    words = text.split(" ")
    _txt_ = ''
    for word in words:
        _before = _txt_
        _txt_ += f"{word} "
        _width, _height = get_text_size(_txt_)
        if _width <= max_width:
            continue
        else:
            if _txt_.strip() == word.strip():
                processed = False
                break
            _wrapped_lines_.append(_before)
            _txt_ = f"{word} "
    _wrapped_lines_.append(_txt_)
    if processed:
        _wrapped_lines_ = [line.strip() for line in _wrapped_lines_]
        result = '\n'.join(_wrapped_lines_).strip()
        height = len(_wrapped_lines_) * height
        # logger.warning(f"wrapped text: {result}")
        return result, height

    _wrapped_lines_ = []
    chars = list(text)
    _txt_ = ''
    for word in chars:
        _txt_ += word
        _width, _height = get_text_size(_txt_)
        if _width <= max_width:
            continue
        else:
            _wrapped_lines_.append(_txt_)
            _txt_ = ''
    _wrapped_lines_.append(_txt_)
    result = '\n'.join(_wrapped_lines_).strip()
    height = len(_wrapped_lines_) * height
    # logger.warning(f"wrapped text: {result}")
    return result, height


def generate_video(video_path: str,
                   audio_path: str,
                   subtitle_path: str,
                   output_file: str,
                   params: VideoParams,
                   ):
    aspect = VideoAspect(params.video_aspect)
    video_width, video_height = aspect.to_resolution()

    logger.info(f"start, video size: {video_width} x {video_height}")
    logger.info(f"  ① video: {video_path}")
    logger.info(f"  ② audio: {audio_path}")
    logger.info(f"  ③ subtitle: {subtitle_path}")
    logger.info(f"  ④ output: {output_file}")

    output_dir = os.path.dirname(output_file)

    font_path = ""
    if params.subtitle_enabled:
        if not params.font_name:
            params.font_name = "STHeitiMedium.ttc"
        font_path = os.path.join(utils.font_dir(), params.font_name)
        if os.name == 'nt':
            font_path = font_path.replace("\\", "/")

        logger.info(f"using font: {font_path}")

    def create_text_clip(subtitle_item):
        phrase = subtitle_item[1]
        max_width = video_width * 0.9
        wrapped_txt, txt_height = wrap_text(phrase,
                                            max_width=max_width,
                                            font=font_path,
                                            fontsize=params.font_size
                                            )
        _clip = TextClip(
            wrapped_txt,
            font=font_path,
            fontsize=params.font_size,
            color=params.text_fore_color,
            bg_color=params.text_background_color,
            stroke_color=params.stroke_color,
            stroke_width=params.stroke_width,
            print_cmd=False,
        )
        duration = subtitle_item[0][1] - subtitle_item[0][0]
        _clip = _clip.set_start(subtitle_item[0][0])
        _clip = _clip.set_end(subtitle_item[0][1])
        _clip = _clip.set_duration(duration)
        if params.subtitle_position == "bottom":
            _clip = _clip.set_position(('center', video_height * 0.95 - _clip.h))
        elif params.subtitle_position == "top":
            _clip = _clip.set_position(('center', video_height * 0.1))
        else:
            _clip = _clip.set_position(('center', 'center'))
        return _clip

    video_clip = VideoFileClip(video_path)
    audio_clip = AudioFileClip(audio_path).volumex(params.voice_volume)

    if subtitle_path and os.path.exists(subtitle_path):
        sub = SubtitlesClip(subtitles=subtitle_path, encoding='utf-8')
        text_clips = []
        for item in sub.subtitles:
            clip = create_text_clip(subtitle_item=item)
            text_clips.append(clip)
        video_clip = CompositeVideoClip([video_clip, *text_clips])

    bgm_file = get_bgm_file(bgm_type=params.bgm_type, bgm_file=params.bgm_file)
    if bgm_file:
        try:
            bgm_clip = (AudioFileClip(bgm_file)
                        .volumex(params.bgm_volume)
                        .audio_fadeout(3))
            bgm_clip = afx.audio_loop(bgm_clip, duration=video_clip.duration)
            audio_clip = CompositeAudioClip([audio_clip, bgm_clip])
        except Exception as e:
            logger.error(f"failed to add bgm: {str(e)}")

    video_clip = video_clip.set_audio(audio_clip)
    video_clip.write_videofile(output_file,
                               audio_codec="aac",
                               temp_audiofile_path=output_dir,
                               threads=params.n_threads or 2,
                               logger=None,
                               fps=30,
                               )

    logger.success(f"completed")


if __name__ == "__main__":
    txt_en = "Here's your guide to travel hacks for budget-friendly adventures"
    txt_zh = "测试长字段这是您的旅行技巧指南帮助您进行预算友好的冒险"
    font = utils.resource_dir() + "/fonts/STHeitiMedium.ttc"
    for txt in [txt_en, txt_zh]:
        t, h = wrap_text(text=txt, max_width=1000, font=font, fontsize=60)
        print(t)

    task_id = "aa563149-a7ea-49c2-b39f-8c32cc225baf"
    task_dir = utils.task_dir(task_id)
    video_file = f"{task_dir}/combined-1.mp4"
    audio_file = f"{task_dir}/audio.mp3"
    subtitle_file = f"{task_dir}/subtitle.srt"
    output_file = f"{task_dir}/final.mp4"

    # video_paths = []
    # for file in os.listdir(utils.storage_dir("test")):
    #     if file.endswith(".mp4"):
    #         video_paths.append(os.path.join(utils.storage_dir("test"), file))
    #
    # combine_videos(combined_video_path=video_file,
    #                audio_file=audio_file,
    #                video_paths=video_paths,
    #                video_aspect=VideoAspect.portrait,
    #                video_concat_mode=VideoConcatMode.random,
    #                max_clip_duration=5,
    #                threads=2)

    cfg = VideoParams()
    cfg.video_aspect = VideoAspect.portrait
    cfg.font_name = "STHeitiMedium.ttc"
    cfg.font_size = 60
    cfg.stroke_color = "#000000"
    cfg.stroke_width = 1.5
    cfg.text_fore_color = "#FFFFFF"
    cfg.text_background_color = "transparent"
    cfg.bgm_type = "random"
    cfg.bgm_file = ""
    cfg.bgm_volume = 1.0
    cfg.subtitle_enabled = True
    cfg.subtitle_position = "bottom"
    cfg.n_threads = 2
    cfg.paragraph_number = 1

    cfg.voice_volume = 1.0

    generate_video(video_path=video_file,
                   audio_path=audio_file,
                   subtitle_path=subtitle_file,
                   output_file=output_file,
                   params=cfg
                   )
