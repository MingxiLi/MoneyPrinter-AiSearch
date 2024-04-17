import streamlit as st
import os.path
import re
from os import path
from moviepy.video.tools.subtitles import SubtitlesClip

from loguru import logger

from app.config import config
from app.models import const
from app.models.schema import VideoParams, VideoConcatMode
from app.services import llm, material, voice, video, subtitle
from app.services import state as sm
from app.utils import utils


def start(task_id, params: VideoParams):
    """
    {
        "video_subject": "",
        "video_aspect": "横屏 16:9（西瓜视频）",
        "voice_name": "女生-晓晓",
        "enable_bgm": false,
        "font_name": "STHeitiMedium 黑体-中",
        "text_color": "#FFFFFF",
        "font_size": 60,
        "stroke_color": "#000000",
        "stroke_width": 1.5
    }
    """
    logger.info(f"start task: {task_id}")
    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=5)

    video_subject = params.video_subject
    voice_name = voice.parse_voice_name(params.voice_name)
    paragraph_number = params.paragraph_number
    n_threads = params.n_threads

    video_script = params.video_script.strip()
    if not video_script:
        logger.info("\n\n## generating video script")
        video_script = llm.generate_script(video_subject=video_subject, language=params.video_language, paragraph_number=paragraph_number)
    else:
        logger.info("\n\n## reuse video script")

    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=10)

    logger.info("\n\n## generating audio")
    audio_file = path.join(utils.task_dir(task_id), f"audio.mp3")
    sub_maker = voice.tts(text=video_script, voice_name=voice_name, voice_file=audio_file)
    if sub_maker is None:
        sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
        logger.error(
            "failed to generate audio, maybe the network is not available. if you are in China, please use a VPN.")
        return

    audio_duration = voice.get_audio_duration(sub_maker)
    logger.info(f"debug audio duration: {audio_duration}")

    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=30)

    subtitle_path = ""
    if params.subtitle_enabled:
        subtitle_path = path.join(utils.task_dir(task_id), f"subtitle.srt")
        subtitle_provider = config.app.get("subtitle_provider", "").strip().lower()

        logger.info(f"\n\n## generating subtitle, provider: {subtitle_provider}")
        subtitle_fallback = False
        
        if subtitle_provider == "edge":
            voice.create_subtitle(text=video_script, sub_maker=sub_maker, subtitle_file=subtitle_path)
            if not os.path.exists(subtitle_path):
                subtitle_fallback = True
                logger.warning("subtitle file not found, fallback to whisper")

        if subtitle_provider == "whisper" or subtitle_fallback:
            subtitle.create(audio_file=audio_file, subtitle_file=subtitle_path)
            logger.info("\n\n## correcting subtitle")
            subtitle.correct(subtitle_file=subtitle_path, video_script=video_script)

        subtitle_lines = subtitle.file_to_subtitles(subtitle_path)
        if not subtitle_lines:
            logger.warning(f"subtitle file is invalid: {subtitle_path}")
            subtitle_path = ""    

    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=40)
    
    video_terms = params.video_terms.strip()
        
    if not video_terms:
        logger.info("\n\n## generating video terms")
        sub = SubtitlesClip(subtitles=subtitle_path, encoding='utf-8')
        video_terms = []
        for subtitle_item in sub.subtitles:
            phrase = subtitle_item[1]
            response_prompt = llm.generate_prompt(subject=params.video_subject, script=phrase)
            duration = subtitle_item[0][1] - subtitle_item[0][0]
            video_terms.append((response_prompt, duration))
            logger.debug(f"debug : {phrase, response_prompt, type(duration)}")
            logger.debug(f"debug : {type(video_terms)}")
    else:
        logger.info("\n\n## reuse video terms")
        sub = SubtitlesClip(subtitles=subtitle_path, encoding='utf-8')
        logger.info(f"debug audio duration: {video_terms}")
        tmp_idx = 0
        tmp_terms = video_terms[1:-1].split(',')
        video_terms = []
        for subtitle_item in sub.subtitles:
            response_prompt = tmp_terms[tmp_idx]
            duration = subtitle_item[0][1] - subtitle_item[0][0]
            video_terms.append((response_prompt, duration))
            logger.debug(f"debug : {response_prompt, type(duration)}")
            logger.debug(f"debug : {type(video_terms)}")
            tmp_idx += 1
        logger.info("\n\n## reuse video terms")
        

    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=20)
    
    logger.info("\n\n## downloading videos")
    downloaded_videos = material.download_videos(task_id=task_id,
                                                 search_terms=video_terms,
                                                 video_aspect=params.video_aspect,
                                                 )
    if not downloaded_videos:
        sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
        logger.error(
            "failed to download videos, maybe the network is not available. if you are in China, please use a VPN.")
        return

    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=50)

    final_video_paths = []
    combined_video_paths = []

    _progress = 50

    combined_video_path = path.join(utils.task_dir(task_id), f"combined.mp4")
    logger.info(f"\n\n## combining video: => {combined_video_path}")
    video.combine_videos(combined_video_path=combined_video_path,
                            video_paths=downloaded_videos,
                            audio_duration=audio_duration,
                             video_aspect=params.video_aspect,
                             threads=n_threads)

    _progress += 50 / 2
    sm.state.update_task(task_id, progress=_progress)

    final_video_path = path.join(utils.task_dir(task_id), f"final.mp4")

    logger.info(f"\n\n## generating video: => {final_video_path}")
    # Put everything together
    video.generate_video(video_path=combined_video_path,
                             audio_path=audio_file,
                             subtitle_path=subtitle_path,
                             output_file=final_video_path,
                             params=params,
                             )

    _progress += 50 / 2
    sm.state.update_task(task_id, progress=_progress)

    final_video_paths.append(final_video_path)
    combined_video_paths.append(combined_video_path)

    logger.success(f"task {task_id} finished, generated {len(final_video_paths)} videos.")

    kwargs = {
        "videos": final_video_paths,
        "combined_videos": combined_video_paths
    }
    sm.state.update_task(task_id, state=const.TASK_STATE_COMPLETE, progress=100, **kwargs)
    return kwargs
