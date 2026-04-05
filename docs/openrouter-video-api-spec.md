# OpenRouter Video Generation Alpha — API Spec

Source: https://openrouter.notion.site/video-generation-testing

## Overview

Video generation is **async**: submit a request → get a job ID → poll for result → download video.

Base URL: `https://openrouter.ai/api/alpha/videos`

## Available Models

| Model | Slug | Duration | Resolution | Aspect Ratio | Image-to-Video |
|-------|------|----------|------------|--------------|----------------|
| Google Veo 3.1 | `google/veo-3.1` | 4s, 6s, 8s | 720p, 1080p, 4K | 16:9, 9:16 | 1 image (i2v), up to 3 reference images |
| OpenAI Sora 2 Pro | `openai/sora-2-pro` | 4s, 8s, 12s, 16s, 20s | 720p, 1080p | 16:9, 9:16 | 1 image |
| ByteDance Seedance 1.5 Pro | `bytedance/seedance-1-5-pro` | 4–12s | 480p, 720p, 1080p | 16:9, 9:16, 4:3, 3:4, 1:1, 21:9 | 1–2 images (first/last frame) |
| Alibaba Wan 2.6 | `alibaba/wan-2.6` | — | 720p, 1080p | 16:9, 9:16 | Yes |

All models support `generate_audio: true`.

## Step 1: Submit Generation

```
POST /api/alpha/videos
Authorization: Bearer $OPENROUTER_API_KEY
Content-Type: application/json
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `model` | string | Yes | Model slug (e.g. `google/veo-3.1`) |
| `prompt` | string | Yes | Text description of the desired video |
| `duration` | integer | No | Duration in seconds (model-dependent) |
| `resolution` | string | No | `480p`, `720p`, `1080p`, `1K`, `2K`, `4K`. Cannot combine with `size`. |
| `aspect_ratio` | string | No | e.g. `16:9`, `9:16`, `1:1`. Can combine with `resolution`. |
| `size` | string | No | Explicit dimensions (e.g. `1280x720`). Alternative to resolution+aspect_ratio. |
| `input_references` | array | No | Image content parts for image-to-video |
| `generate_audio` | boolean | No | Co-generate audio (model-dependent) |
| `seed` | integer | No | For reproducible generations |

### Example Request Body

```json
{
  "model": "google/veo-3.1",
  "prompt": "A teddy bear playing electric guitar on stage at a concert",
  "aspect_ratio": "16:9",
  "duration": 4,
  "resolution": "1080p",
  "generate_audio": true
}
```

### Response (HTTP 202)

```json
{
  "id": "vgen_abc123def456",
  "polling_url": "https://openrouter.ai/api/alpha/videos/vgen_abc123def456",
  "status": "pending"
}
```

Credits are placed on hold when job is created. Hold is finalized on completion, released on failure.

## Step 2: Poll for Status

```
GET /api/alpha/videos/:jobId
Authorization: Bearer $OPENROUTER_API_KEY
```

Poll every ~30 seconds until `status` is `completed` or `failed`.

### Completed Response

```json
{
  "id": "vgen_abc123def456",
  "polling_url": "https://openrouter.ai/api/alpha/videos/vgen_abc123def456",
  "status": "completed",
  "unsigned_urls": [
    "https://openrouter.ai/api/alpha/videos/vgen_abc123def456/content?index=0"
  ],
  "usage": {
    "cost": 3.2,
    "is_byok": false
  },
  "generation_id": "gen-vid-...."
}
```

### Failed Response

```json
{
  "id": "vgen_abc123def456",
  "polling_url": "https://openrouter.ai/api/alpha/videos/vgen_abc123def456",
  "status": "failed",
  "error": "Content moderation: prompt was flagged"
}
```

### Statuses

| Status | Meaning |
|--------|---------|
| `pending` | Job accepted, queued |
| `in_progress` | Generation in progress |
| `completed` | Done. `unsigned_urls` populated. |
| `failed` | Error. Check `error` field. |
| `cancelled` | Job was cancelled |
| `expired` | Job expired before completing |

## Step 3: Download the Video

```
GET /api/alpha/videos/:jobId/content
Authorization: Bearer $OPENROUTER_API_KEY
```

Returns raw video bytes (MP4).

**Warning:** Video URLs are temporary (1-48 hours). Download promptly.

## Image-to-Video

Pass image references via `input_references`:

```json
{
  "model": "google/veo-3.1",
  "prompt": "The scene comes to life with gentle motion",
  "input_references": [
    {
      "type": "image_url",
      "image_url": {
        "url": "https://example.com/my-image.jpg"
      }
    }
  ]
}
```

## Capability Discovery

```
GET /api/alpha/videos/models
```

Returns metadata per model: supported resolutions, aspect ratios, sizes, pricing SKUs, and passthrough parameters.

### Example Response (Wan 2.6)

```json
{
  "data": [
    {
      "id": "alibaba/wan-2.6",
      "name": "Alibaba: Wan 2.6 (experimental)",
      "supported_resolutions": ["720p", "1080p"],
      "supported_aspect_ratios": ["16:9", "9:16"],
      "supported_sizes": ["1280x720", "1080x1920", "720x1280", "1920x1080"],
      "pricing_skus": {
        "text_to_video_duration_seconds_480p": "0.04",
        "text_to_video_duration_seconds_720p": "0.08",
        "image_to_video_duration_seconds_720p": "0.10",
        "text_to_video_duration_seconds_1080p": "0.12",
        "image_to_video_duration_seconds_1080p": "0.15"
      },
      "allowed_passthrough_parameters": [
        "negative_prompt", "enable_prompt_expansion", "shot_type", "audio", "size"
      ]
    }
  ]
}
```

## Passthrough Parameters

Provider-specific params via `provider.options`:

```json
{
  "model": "alibaba/wan-2.6",
  "prompt": "A cat sitting on a windowsill watching rain",
  "resolution": "720p",
  "duration": 5,
  "provider": {
    "options": {
      "atlas-cloud": {
        "audio": "https://example.com/audio.mp3"
      }
    }
  }
}
```

## Known Limitations

- No SDK support (coming at v1)
- No cancel or delete endpoints
- API spec may change during alpha
- Billing is live (credits on hold during generation)
