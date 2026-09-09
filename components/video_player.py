"""Embedded YouTube video helper."""

from __future__ import annotations

import streamlit as st


def embed_video(video_id: str, height: int = 360) -> None:
    st.video(f"https://www.youtube.com/watch?v={video_id}")


def video_thumbnail(thumbnail_url: str | None, video_url: str | None) -> None:
    if thumbnail_url:
        if video_url:
            st.markdown(
                f'<a href="{video_url}" target="_blank"><img src="{thumbnail_url}" '
                f'style="width:100%;border-radius:6px;"></a>',
                unsafe_allow_html=True,
            )
        else:
            st.image(thumbnail_url, width='stretch')
