import { describe, expect, it } from 'vitest';
import { embedUrl } from './playback';

const origin = 'https://digest.example';

describe('embedUrl', () => {
  it('builds a YouTube embed with the JS API enabled from any YouTube URL', () => {
    for (const url of [
      'https://www.youtube.com/embed/Lx9qTrAnZ4c',
      'https://www.youtube.com/watch?v=Lx9qTrAnZ4c&t=10s',
      'https://youtu.be/Lx9qTrAnZ4c',
      'https://www.youtube.com/shorts/Lx9qTrAnZ4c',
    ]) {
      expect(embedUrl('youtube', url, origin)).toBe(
        'https://www.youtube.com/embed/Lx9qTrAnZ4c?enablejsapi=1&playsinline=1&rel=0&origin=https%3A%2F%2Fdigest.example',
      );
    }
  });

  it('converts a Rutube page URL and keeps an embed URL', () => {
    const id = '0c1a57c0eefced6be40db07dbfd9d8e3';
    expect(embedUrl('rutube', `https://rutube.ru/video/${id}/`, origin)).toBe(
      `https://rutube.ru/play/embed/${id}`,
    );
    expect(embedUrl('rutube', `https://rutube.ru/play/embed/${id}`, origin)).toBe(
      `https://rutube.ru/play/embed/${id}`,
    );
    expect(embedUrl('rutube', `https://rutube.ru/video/private/${id}/?p=KEY`, origin)).toBe(
      `https://rutube.ru/play/embed/${id}?p=KEY`,
    );
  });

  it('converts a VK page URL to video_ext.php with js_api and keeps an embed URL', () => {
    expect(embedUrl('vk', 'https://vk.com/video-22822305_456241864', origin)).toBe(
      'https://vk.com/video_ext.php?oid=-22822305&id=456241864&js_api=1',
    );
    expect(embedUrl('vk', 'https://vkvideo.ru/video-1_2', origin)).toBe(
      'https://vk.com/video_ext.php?oid=-1&id=2&js_api=1',
    );
    expect(embedUrl('vk', 'https://vk.com/video_ext.php?oid=-1&id=2&hash=abc', origin)).toBe(
      'https://vk.com/video_ext.php?oid=-1&id=2&hash=abc&js_api=1',
    );
  });

  it('returns null for URLs it cannot read', () => {
    expect(embedUrl('youtube', 'https://example.org/v', origin)).toBeNull();
    expect(embedUrl('vk', 'https://vk.com/feed', origin)).toBeNull();
    expect(embedUrl('direct', 'https://example.org/a.mp4', origin)).toBeNull();
  });
});
