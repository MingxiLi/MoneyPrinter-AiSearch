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
                  duration: float,
                  video_aspect: VideoAspect = VideoAspect.portrait,
                  ) -> List[MaterialInfo]:
    aspect = VideoAspect(video_aspect)

    text_feature = process_text(search_term)
    video_list = search_pexels_video_by_feature(text_feature)
    video_items = []
    
    sampled_duration = 0.
    idx = 0
    
    while sampled_duration < duration:
        sampled_video = video_list[idx]
        duration = sampled_video["duration"]
        
        item = MaterialInfo()
        item.provider = "pexels"
        item.url = 'https://www.pexels.com/download/video/' + sampled_video["thumbnail_loc"].split('/')[4]
        item.duration = sampled_video["duration"]
        video_items.append(item)
        
        sampled_duration += duration
        idx += 1    
        
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
                    search_terms: List = [(str, float)],
                    video_aspect: VideoAspect = VideoAspect.portrait,
                    ) -> List[str]:
    video_paths = []
    valid_video_urls = []
    
    material_directory = config.app.get("material_directory", "").strip()
    if material_directory == "task":
        material_directory = utils.task_dir(task_id)
    elif material_directory and not os.path.isdir(material_directory):
        material_directory = ""
    
    for search_term in search_terms:
        logger.info(f"searching videos for '{search_term}'")
        
        text_feature = process_text(search_term[0])
        video_list = search_pexels_video_by_feature(text_feature)
        
        cur_sampled_duration = 0.
        idx = 0
        
        while cur_sampled_duration < search_term[1]:
            sampled_video = video_list[idx]
            cur_url = 'https://www.pexels.com/download/video/' + sampled_video["thumbnail_loc"].split('/')[4]
            
            if cur_url not in valid_video_urls:
                logger.info(f"downloading video: {cur_url}")
                saved_video_path = save_video(video_url=cur_url, save_dir=material_directory)
                
                if saved_video_path:
                    cur_clip = VideoFileClip(saved_video_path).without_audio()
                    cur_clip = cur_clip.set_fps(30)
                    
                    if (cur_sampled_duration + cur_clip.duration) > search_term[1]:
                        cur_clip = cur_clip.subclip(0, (search_term[1] - cur_sampled_duration + 0.2))
                    
                    post_str = os.path.splitext(saved_video_path)[-1]
                    saved_video_clip_path = saved_video_path.replace(post_str, '_clip' + post_str)
                    
                    cur_clip.write_videofile(
                            filename=saved_video_clip_path,
                            threads=2,
                            logger=None,
                            audio_codec="aac",
                            fps=30,
                        )
                    
                    logger.info(f"video saved: {saved_video_clip_path}")
                    video_paths.append(saved_video_clip_path)
                    
                    cur_sampled_duration += cur_clip.duration
                    valid_video_urls.append(cur_url)
            idx += 1

    logger.success(f"downloaded {len(video_paths)} videos")
    return video_paths


if __name__ == "__main__":
    download_videos("test123", ["cat"], audio_duration=100)
