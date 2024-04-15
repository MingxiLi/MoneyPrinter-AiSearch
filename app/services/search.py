import numpy as np
from loguru import logger
from sqlalchemy import BINARY, Column, DateTime, Integer, String
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from transformers import AutoModelForZeroShotImageClassification, AutoProcessor

from app.config import config


logger.info("Loading model...")
model = AutoModelForZeroShotImageClassification.from_pretrained(config.nn_model_name)
processor = AutoProcessor.from_pretrained(config.nn_model_name)
logger.info("Model loaded.")


BaseModelPexelsVideo = declarative_base()
engine_pexels_video = create_engine(
    'sqlite:///./resource/database/PexelsVideo.db',
    connect_args={"check_same_thread": False}
)
DatabaseSessionPexelsVideo = sessionmaker(autocommit=False, autoflush=False, bind=engine_pexels_video)
BaseModelPexelsVideo.metadata.create_all(bind=engine_pexels_video)


class PexelsVideo(BaseModelPexelsVideo):
    __tablename__ = "PexelsVideo"
    id = Column(Integer, primary_key=True)
    title = Column(String(128))
    thumbnail_loc = Column(String(256), index=True)
    content_loc = Column(String(256))
    thumbnail_feature = Column(BINARY)
    duration = Column(Integer, index=True)


def process_text(input_text):
    if not input_text:
        return None
    text = processor(text=input_text, return_tensors="pt", padding=True)["input_ids"]
    text_features = model.get_text_features(text).detach().cpu().numpy()
    return text_features


def normalize_features(features):
    return features / np.linalg.norm(features, axis=1, keepdims=True)


def match_batch(
        positive_feature,
        image_features,
):
    new_features = normalize_features(image_features)
    new_text_positive_feature = positive_feature / np.linalg.norm(positive_feature)
    positive_scores = new_features @ new_text_positive_feature.T

    scores = positive_scores
    
    return scores


def get_pexels_video_features(session: Session):
    query = session.query(
        PexelsVideo.thumbnail_feature, PexelsVideo.thumbnail_loc, PexelsVideo.content_loc,
        PexelsVideo.title, PexelsVideo.duration
    ).all()
    try:
        thumbnail_feature_list, thumbnail_loc_list, content_loc_list, title_list, duration_list = zip(*query)
        return thumbnail_feature_list, thumbnail_loc_list, content_loc_list, title_list, duration_list
    except ValueError:
        return [], [], [], [], []


def search_pexels_video_by_feature(positive_feature):
    with DatabaseSessionPexelsVideo() as session:
        thumbnail_feature_list, thumbnail_loc_list, content_loc_list, title_list, duration_list = get_pexels_video_features(session)
        
    if len(thumbnail_feature_list) == 0:
        return []
    
    thumbnail_features = np.frombuffer(b"".join(thumbnail_feature_list), dtype=np.float32).reshape(len(thumbnail_feature_list), -1)
    thumbnail_scores = match_batch(positive_feature, thumbnail_features)
    return_list = []
    for score, thumbnail_loc, content_loc, title, duration in zip(
            thumbnail_scores, thumbnail_loc_list, content_loc_list, title_list, duration_list
    ):
        if not score:
            continue
        return_list.append({
            "thumbnail_loc": thumbnail_loc,
            "content_loc": content_loc,
            "title": title,
            "score": float(score.max()),
            "duration": duration,
        })
    return_list = sorted(return_list, key=lambda x: x["score"], reverse=True)
    return return_list
