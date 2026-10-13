/* Generated from ../schemas/result.schema.json by npm run gen:types. Do not edit. */

export type NullableString = string | null;
/**
 * ISO 639-1
 */
export type Lang = string;
export type Option =
  'glossary' | 'critique' | 'self_check' | 'action_items' | 'decisions' | 'questions';
/**
 * seconds from the start of the video
 */
export type Timecode = number;

/**
 * Machine-readable twin of docs/result-schema.md (v1.0). The markdown wins on any discrepancy. Semantic rules of section 9 (starts within duration, quotes found in transcript.clean, verdict needs sources, tldr <= 80 words) are checked by n8n/scripts/validate_result.py, not here.
 */
export interface VideoDigestResult {
  schema_version: '1.0';
  job_id: string;
  source: Source;
  preset: 'lecture' | 'meeting' | 'talk' | 'interview' | 'plain';
  options: Option[];
  output_language: Lang;
  transcript: Transcript;
  digest: Digest;
  extras: Extras;
  meta: Meta;
  /**
   * What changes what the reader reads (2026-09-23): transcript_shortened – clean kept less than the rule allows and the correction did not bring it all back; clean_fallback – chunks cleaned by rules without the model. places counts the units, starts lists their timecodes (sorted, unique, at most 40). Style warnings stay in jobs.meta.quality_warnings.
   */
  notices?: {
    kind: 'transcript_shortened' | 'clean_fallback';
    places: number;
    /**
     * @maxItems 40
     */
    starts: Timecode[];
  }[];
}
export interface Source {
  type: 'url' | 'upload';
  url: NullableString;
  /**
   * yt-dlp extractor name or 'upload'
   */
  platform: string;
  title: string;
  duration_sec: number;
  thumbnail_url: NullableString;
  language: Lang;
  /**
   * request: the code came from the job as is, the STT provider detected nothing (Deepgram with a fixed language)
   */
  language_detected_by: 'subtitles' | 'whisper' | 'request' | 'llm';
  /**
   * null when the provider reports no probability (OpenAI whisper-1, Deepgram with a fixed language)
   */
  language_confidence: number | null;
  playback: {
    kind: 'youtube' | 'vk' | 'rutube' | 'direct' | 'audio';
    url: string;
    has_video: boolean;
  };
}
export interface Transcript {
  origin: 'subtitles_manual' | 'subtitles_auto' | 'whisper' | 'deepgram';
  /**
   * @minItems 1
   */
  segments: [Segment, ...Segment[]];
  /**
   * @minItems 1
   */
  clean: [Paragraph, ...Paragraph[]];
  stats: {
    words: number;
    segments: number;
    /**
     * null: not measured (whisper separates nobody, Deepgram numbers speakers per chunk)
     */
    speakers: number | null;
  };
}
export interface Segment {
  start: Timecode;
  end: Timecode;
  text: string;
  /**
   * Deepgram: "<chunk>:<n>", the speaker number is local to the audio chunk, there is no cross-chunk identity; null for subtitles and whisper
   */
  speaker: string | null;
}
export interface Paragraph {
  start: Timecode;
  text: string;
}
export interface Digest {
  tldr: string;
  /**
   * @minItems 1
   * @maxItems 12
   */
  key_points:
    | [
        {
          text: string;
          detail: string;
          start: Timecode;
        },
      ]
    | [
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
      ]
    | [
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
      ]
    | [
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
      ]
    | [
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
      ]
    | [
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
      ]
    | [
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
      ]
    | [
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
      ]
    | [
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
      ]
    | [
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
      ]
    | [
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
      ]
    | [
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
        {
          text: string;
          detail: string;
          start: Timecode;
        },
      ];
  /**
   * Parts sorted by start, contiguous: structure[0].start = 0, structure[i].end = structure[i+1].start, last end = source.duration_sec. Not expressible in JSON Schema; enforced by n8n/scripts/validate_result.py and the digest-reduce check in n8n.
   *
   * @minItems 1
   * @maxItems 10
   */
  structure:
    | [
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
      ]
    | [
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
      ]
    | [
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
      ]
    | [
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
      ]
    | [
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
      ]
    | [
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
      ]
    | [
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
      ]
    | [
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
      ]
    | [
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
      ]
    | [
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
        {
          title: string;
          start: Timecode;
          end: Timecode;
          summary: string;
        },
      ];
  /**
   * translation is required and non-empty when output_language differs from source.language, null otherwise (checked by validate_result.py and llm-call).
   *
   * @minItems 1
   * @maxItems 8
   */
  quotes:
    | [
        {
          text: string;
          translation: NullableString;
          start: Timecode;
          speaker: NullableString;
        },
      ]
    | [
        {
          text: string;
          translation: NullableString;
          start: Timecode;
          speaker: NullableString;
        },
        {
          text: string;
          translation: NullableString;
          start: Timecode;
          speaker: NullableString;
        },
      ]
    | [
        {
          text: string;
          translation: NullableString;
          start: Timecode;
          speaker: NullableString;
        },
        {
          text: string;
          translation: NullableString;
          start: Timecode;
          speaker: NullableString;
        },
        {
          text: string;
          translation: NullableString;
          start: Timecode;
          speaker: NullableString;
        },
      ]
    | [
        {
          text: string;
          translation: NullableString;
          start: Timecode;
          speaker: NullableString;
        },
        {
          text: string;
          translation: NullableString;
          start: Timecode;
          speaker: NullableString;
        },
        {
          text: string;
          translation: NullableString;
          start: Timecode;
          speaker: NullableString;
        },
        {
          text: string;
          translation: NullableString;
          start: Timecode;
          speaker: NullableString;
        },
      ]
    | [
        {
          text: string;
          translation: NullableString;
          start: Timecode;
          speaker: NullableString;
        },
        {
          text: string;
          translation: NullableString;
          start: Timecode;
          speaker: NullableString;
        },
        {
          text: string;
          translation: NullableString;
          start: Timecode;
          speaker: NullableString;
        },
        {
          text: string;
          translation: NullableString;
          start: Timecode;
          speaker: NullableString;
        },
        {
          text: string;
          translation: NullableString;
          start: Timecode;
          speaker: NullableString;
        },
      ]
    | [
        {
          text: string;
          translation: NullableString;
          start: Timecode;
          speaker: NullableString;
        },
        {
          text: string;
          translation: NullableString;
          start: Timecode;
          speaker: NullableString;
        },
        {
          text: string;
          translation: NullableString;
          start: Timecode;
          speaker: NullableString;
        },
        {
          text: string;
          translation: NullableString;
          start: Timecode;
          speaker: NullableString;
        },
        {
          text: string;
          translation: NullableString;
          start: Timecode;
          speaker: NullableString;
        },
        {
          text: string;
          translation: NullableString;
          start: Timecode;
          speaker: NullableString;
        },
      ]
    | [
        {
          text: string;
          translation: NullableString;
          start: Timecode;
          speaker: NullableString;
        },
        {
          text: string;
          translation: NullableString;
          start: Timecode;
          speaker: NullableString;
        },
        {
          text: string;
          translation: NullableString;
          start: Timecode;
          speaker: NullableString;
        },
        {
          text: string;
          translation: NullableString;
          start: Timecode;
          speaker: NullableString;
        },
        {
          text: string;
          translation: NullableString;
          start: Timecode;
          speaker: NullableString;
        },
        {
          text: string;
          translation: NullableString;
          start: Timecode;
          speaker: NullableString;
        },
        {
          text: string;
          translation: NullableString;
          start: Timecode;
          speaker: NullableString;
        },
      ]
    | [
        {
          text: string;
          translation: NullableString;
          start: Timecode;
          speaker: NullableString;
        },
        {
          text: string;
          translation: NullableString;
          start: Timecode;
          speaker: NullableString;
        },
        {
          text: string;
          translation: NullableString;
          start: Timecode;
          speaker: NullableString;
        },
        {
          text: string;
          translation: NullableString;
          start: Timecode;
          speaker: NullableString;
        },
        {
          text: string;
          translation: NullableString;
          start: Timecode;
          speaker: NullableString;
        },
        {
          text: string;
          translation: NullableString;
          start: Timecode;
          speaker: NullableString;
        },
        {
          text: string;
          translation: NullableString;
          start: Timecode;
          speaker: NullableString;
        },
        {
          text: string;
          translation: NullableString;
          start: Timecode;
          speaker: NullableString;
        },
      ];
}
/**
 * Only ordered blocks are present; each key is optional.
 */
export interface Extras {
  glossary?: {
    term: string;
    definition: string;
    start: Timecode;
  }[];
  decisions?: TimedText[];
  action_items?: {
    text: string;
    owner: NullableString;
    due: NullableString;
    start: Timecode;
  }[];
  questions?: TimedText[];
  critique?: {
    strong: string[];
    weak: {
      claim: string;
      issue: string;
      start: Timecode;
    }[];
    missing: string[];
  };
  self_check?: {
    question: string;
    answer: string;
    start: Timecode;
  }[];
}
export interface TimedText {
  text: string;
  start: Timecode;
}
export interface Meta {
  created_at: string;
  finished_at: string;
  stages: Stage[];
  total_cost_usd: number;
  tokens: {
    in: number;
    out: number;
  };
}
export interface Stage {
  /**
   * fact_check: stage of results stored before 2026-09-17 only, never produced anything
   */
  name: 'probe' | 'download' | 'transcribe' | 'clean' | 'digest' | 'extras' | 'fact_check';
  status: 'pending' | 'running' | 'done' | 'failed' | 'skipped';
  ms: number;
  cost_usd: number;
  provider?: string;
  model?: string;
  /**
   * the model id from the provider's answer (OpenAI snapshot, Deepgram name and build), next to the requested model
   */
  model_actual?: string;
  error?: string;
}
