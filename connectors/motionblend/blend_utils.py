"""
Motion Blending Utilities for MotionBlend Connector

Provides simplified motion blending calculations for cataloging blend operations.
This module focuses on metadata and blend parameter computation, not actual
motion synthesis (which requires deep learning models from the blendanim framework).

For full motion blending with neural networks, see: https://github.com/RydlrCS/blendanim
"""

import hashlib  # For generating deterministic blend IDs using SHA-1 hashing
from typing import Any  # For type hints to improve code clarity and IDE support
from datetime import datetime, timezone  # For generating UTC timestamps in ISO 8601 format


def calculate_blend_ratio(
    left_duration: float, right_duration: float, transition_frames: int = 30
) -> float:
    """
    Calculate blend ratio based on motion durations.

    Args:
        left_duration: Duration of left motion in seconds
        right_duration: Duration of right motion in seconds
        transition_frames: Number of frames for transition (default: 30 at 30fps = 1 second)

    Returns:
        Blend ratio between 0.0 and 1.0
    """
    total_duration = left_duration + right_duration
    if total_duration == 0:
        return 0.5

    # Weight based on duration - longer motion gets higher weight
    ratio = left_duration / total_duration

    # Clamp to valid range
    return max(0.0, min(1.0, ratio))


def calculate_transition_window(
    left_frames: int, right_frames: int, blend_ratio: float = 0.5, window_size: int = 30
) -> tuple[int, int]:
    """
    Calculate transition start and end frames for blending.

    Args:
        left_frames: Total frames in left motion
        right_frames: Total frames in right motion
        blend_ratio: Blend ratio (0.0 = left dominant, 1.0 = right dominant)
        window_size: Size of transition window in frames

    Returns:
        Tuple of (transition_start_frame, transition_end_frame)
    """
    # Calculate transition point based on blend ratio
    # 0.5 ratio = blend at midpoint of left motion
    # Higher ratio = blend later in left motion
    transition_point = int(left_frames * blend_ratio)

    # Calculate window around transition point
    half_window = window_size // 2
    start_frame = max(0, transition_point - half_window)
    end_frame = min(left_frames, transition_point + half_window)

    # Ensure minimum window size
    if (end_frame - start_frame) < window_size:
        # Adjust to maintain window size if possible
        if start_frame == 0:
            end_frame = min(left_frames, start_frame + window_size)
        elif end_frame == left_frames:
            start_frame = max(0, end_frame - window_size)

    return (start_frame, end_frame)


def generate_blend_id(left_motion_uri: str, right_motion_uri: str) -> str:
    """
    Generate deterministic blend ID from motion pair URIs.

    Args:
        left_motion_uri: URI of left motion file
        right_motion_uri: URI of right motion file

    Returns:
        16-character SHA-1 hash prefix of concatenated URIs
    """
    combined = f"{left_motion_uri}|{right_motion_uri}"
    return hashlib.sha1(combined.encode("utf-8")).hexdigest()[:16]


def estimate_blend_quality(
    left_frames: int, right_frames: int, blend_ratio: float, transition_window_size: int
) -> float | None:
    """
    Estimate blend quality score based on motion parameters.

    This is a simple heuristic - actual quality requires motion analysis.
    For real quality metrics, use the blendanim framework's L2 velocity metrics.

    Args:
        left_frames: Frames in left motion
        right_frames: Frames in right motion
        blend_ratio: Blend ratio used
        transition_window_size: Size of transition window

    Returns:
        Quality score between 0.0 and 1.0, or None if insufficient data
    """
    if left_frames == 0 or right_frames == 0:
        return None

    # Factors affecting blend quality:
    # 1. Similar durations (0.3 weight)
    duration_diff = abs(left_frames - right_frames)
    max_frames = max(left_frames, right_frames)
    if max_frames > 0:
        duration_similarity = 1.0 - min(1.0, duration_diff / max_frames)
    else:
        duration_similarity = 0.0

    # 2. Reasonable transition window (0.3 weight)
    # Window should be 10-50% of shorter motion
    min_frames = min(left_frames, right_frames)
    if min_frames == 0:
        return None  # Cannot calculate quality for zero-length motions

    ideal_window_ratio = 0.3  # 30% of motion
    actual_window_ratio = transition_window_size / min_frames
    window_quality = 1.0 - abs(actual_window_ratio - ideal_window_ratio)
    window_quality = max(0.0, min(1.0, window_quality))

    # 3. Balanced blend ratio (0.4 weight)
    # Closer to 0.5 is generally better for smooth transitions
    ratio_balance = 1.0 - abs(blend_ratio - 0.5) * 2.0

    # Weighted combination
    quality = duration_similarity * 0.3 + window_quality * 0.3 + ratio_balance * 0.4

    return round(quality, 3)


def create_blend_metadata(
    left_motion: dict[str, Any],
    right_motion: dict[str, Any],
    transition_frames: int = 30,
    custom_ratio: float | None = None,
) -> dict[str, Any]:
    """
    Create blend metadata record from two motion files.

    Args:
        left_motion: Left motion record with 'file_uri', 'frames', 'updated_at'
        right_motion: Right motion record with 'file_uri', 'frames', 'updated_at'
        transition_frames: Number of frames for transition window
        custom_ratio: Optional custom blend ratio (auto-calculated if None)

    Returns:
        Dictionary with blend metadata
    """
    left_frames = left_motion.get("frames", 0)
    right_frames = right_motion.get("frames", 0)

    # Calculate or use custom blend ratio
    if custom_ratio is not None:
        blend_ratio = max(0.0, min(1.0, custom_ratio))
    else:
        # Estimate based on frame counts (assuming 30fps)
        left_duration = left_frames / 30.0
        right_duration = right_frames / 30.0
        blend_ratio = calculate_blend_ratio(left_duration, right_duration, transition_frames)

    # Calculate transition window
    start_frame, end_frame = calculate_transition_window(
        left_frames, right_frames, blend_ratio, transition_frames
    )

    # Estimate quality
    quality = estimate_blend_quality(left_frames, right_frames, blend_ratio, transition_frames)

    # Generate unique blend ID
    blend_id = generate_blend_id(left_motion["file_uri"], right_motion["file_uri"])

    # Create metadata record
    now = datetime.now(timezone.utc).isoformat()

    return {
        "id": blend_id,
        "left_motion_id": left_motion.get("id"),
        "right_motion_id": right_motion.get("id"),
        "left_motion_uri": left_motion["file_uri"],
        "right_motion_uri": right_motion["file_uri"],
        "blend_ratio": round(blend_ratio, 3),
        "transition_start_frame": start_frame,
        "transition_end_frame": end_frame,
        "transition_frames": end_frame - start_frame,
        "estimated_quality": quality,
        "transition_smoothness": None,  # Requires actual motion analysis
        "created_at": left_motion.get("updated_at", now),
        "updated_at": max(left_motion.get("updated_at", now), right_motion.get("updated_at", now)),
    }


def generate_blend_pairs(
    seed_motions: list, build_motions: list, max_pairs: int | None = None
) -> list:
    """
    Generate blend motion pairs from seed and build motions.

    Strategy: Pair each build motion with compatible seed motions.
    Early termination when max_pairs is reached to avoid O(n*m) complexity issues.

    Args:
        seed_motions: List of seed motion records
        build_motions: List of build motion records
        max_pairs: Optional maximum number of pairs to generate

    Returns:
        List of blend metadata records
    """
    blends = []

    for build_motion in build_motions:
        # Early termination in outer loop to avoid unnecessary iterations
        if max_pairs and len(blends) >= max_pairs:
            break

        for seed_motion in seed_motions:
            # Create blend pairing
            blend = create_blend_metadata(seed_motion, build_motion)
            blends.append(blend)

            # Check limit immediately to avoid unnecessary iterations
            if max_pairs and len(blends) >= max_pairs:
                return blends

    return blends
