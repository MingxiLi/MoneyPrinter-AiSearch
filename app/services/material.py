import os
import random
from urllib.parse import urlencode

import requests
from typing import List
from loguru import logger
from moviepy.video.io.VideoFileClip import VideoFileClip

from app.config import config
from app.models.schema import VideoAspect, VideoConcatMode, MaterialInfo
from app.utils import utils
from app.services.search import process_text, search_pexels_video_by_feature

requested_count = 0


def search_videos(search_term: str,
                  minimum_duration: int,
                  video_aspect: VideoAspect = VideoAspect.portrait,
                  ) -> List[MaterialInfo]:
    aspect = VideoAspect(video_aspect)

    text_feature = process_text(search_term)
    video_list = search_pexels_video_by_feature(text_feature)[:10]
    video_items = []
    
    # sampled_video = random.choice(video_list)
    sampled_video = video_list[0]
    duration = sampled_video["duration"]
    while duration < minimum_duration:
        sampled_video = random.choice(video_list)
        duration = sampled_video["duration"]

    item = MaterialInfo()
    item.provider = "pexels"
    item.url = 'https://www.pexels.com/download/video/' + sampled_video["thumbnail_loc"].split('/')[4]
    item.duration = sampled_video["duration"]
    video_items.append(item)
        
    return video_items


def save_video(video_url: str, save_dir: str = "") -> str:
    if not save_dir:
        save_dir = utils.storage_dir("cache_videos")

    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    url_without_query = video_url.split("?")[0]
    url_hash = utils.md5(url_without_query)
    video_id = f"vid-{url_hash}"
    video_path = f"{save_dir}/{video_id}.mp4"

    # if video already exists, return the path
    if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
        logger.info(f"video already exists: {video_path}")
        return video_path

    # if video does not exist, download it
    proxies = config.pexels.get("proxies", None)
    with open(video_path, "wb") as f:
        f.write(requests.get(video_url, proxies=proxies, verify=False, timeout=(60, 240)).content)

    if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
        try:
            clip = VideoFileClip(video_path)
            duration = clip.duration
            fps = clip.fps
            clip.close()
            if duration > 0 and fps > 0:
                return video_path
        except Exception as e:
            try:
                os.remove(video_path)
            except Exception as e:
                pass
            logger.warning(f"invalid video file: {video_path} => {str(e)}")
    return ""


def download_videos(task_id: str,
                    search_terms: List[str],
                    video_aspect: VideoAspect = VideoAspect.portrait,
                    video_contact_mode: VideoConcatMode = VideoConcatMode.random,
                    audio_duration: float = 0.0,
                    max_clip_duration: int = 5,
                    ) -> List[str]:
    valid_video_items = []
    valid_video_urls = []
    found_duration = 0.0
    for search_term in search_terms:
        logger.info(f"searching videos for '{search_term}'")
        video_items = search_videos(search_term=search_term,
                                    minimum_duration=max_clip_duration,
                                    video_aspect=video_aspect)
        logger.info(f"found {len(video_items)} videos for '{search_term}'")

        for item in video_items:
            if item.url not in valid_video_urls:
                valid_video_items.append(item)
                valid_video_urls.append(item.url)
                found_duration += item.duration

    logger.info(
        f"found total videos: {len(valid_video_items)}, required duration: {audio_duration} seconds, found duration: {found_duration} seconds")
    video_paths = []

    material_directory = config.app.get("material_directory", "").strip()
    if material_directory == "task":
        material_directory = utils.task_dir(task_id)
    elif material_directory and not os.path.isdir(material_directory):
        material_directory = ""

    if video_contact_mode.value == VideoConcatMode.random.value:
        random.shuffle(valid_video_items)

    total_duration = 0.0
    for item in valid_video_items:
        try:
            logger.info(f"downloading video: {item.url}")
            saved_video_path = save_video(video_url=item.url, save_dir=material_directory)
            if saved_video_path:
                logger.info(f"video saved: {saved_video_path}")
                video_paths.append(saved_video_path)
                seconds = min(max_clip_duration, item.duration)
                total_duration += seconds
                if total_duration > audio_duration:
                    logger.info(f"total duration of downloaded videos: {total_duration} seconds, skip downloading more")
                    break
        except Exception as e:
            logger.error(f"failed to download video: {utils.to_json(item)} => {str(e)}")
    logger.success(f"downloaded {len(video_paths)} videos")
    return video_paths


if __name__ == "__main__":
    download_videos("test123", ["cat"], audio_duration=100)
