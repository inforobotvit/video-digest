import { formatTimecode } from '@/lib/timecode';

interface Props {
  seconds: number;
  color?: string;
  className?: string;
  onSeek?: (seconds: number) => void;
  title?: string;
}

/** Monospace, clickable timecode. Seeks the player; never navigates away. `tc--now` marks the player's row. */
export function Timecode({ seconds, color, className, onSeek, title }: Props) {
  return (
    <button
      type="button"
      className={`tc ${className ?? ''}`}
      style={color ? { color } : undefined}
      onClick={() => onSeek?.(seconds)}
      title={title}
    >
      {formatTimecode(seconds)}
    </button>
  );
}
