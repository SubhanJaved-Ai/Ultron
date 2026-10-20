import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import {
  fetchVoiceSettings,
  updateVoiceSettings,
  testElevenLabsConnection,
  fetchElevenLabsVoices,
  fetchElevenLabsModels,
  previewElevenLabsVoice,
} from './api';

describe('Voice Settings and ElevenLabs API Client', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('fetchVoiceSettings retrieves configuration with masked API key', async () => {
    const mockResponse = {
      provider: 'system',
      voice_id: 'JBFqnCBsd6RMkjVDRZzb',
      model_id: 'eleven_turbo_v2_5',
      stability: 0.5,
      similarity_boost: 0.75,
      style: 0.0,
      speed: 1.0,
      has_api_key: true,
      masked_api_key: '••••••••abcd',
      available_providers: [
        { id: 'system', name: 'System Default', available: true },
        { id: 'elevenlabs', name: 'ElevenLabs', available: true },
      ],
    };

    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => mockResponse,
    } as unknown as Response);

    const settings = await fetchVoiceSettings();
    expect(settings.provider).toBe('system');
    expect(settings.has_api_key).toBe(true);
    expect(settings.masked_api_key).toBe('••••••••abcd');
    expect(settings.available_providers?.length).toBe(2);
  });

  it('updateVoiceSettings sends changes and returns updated settings', async () => {
    const updatedResponse = {
      provider: 'elevenlabs',
      voice_id: 'custom-voice-id',
      model_id: 'eleven_multilingual_v2',
      stability: 0.7,
      similarity_boost: 0.85,
      style: 0.15,
      speed: 1.2,
      has_api_key: true,
      masked_api_key: '••••••••5555',
    };

    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => updatedResponse,
    } as unknown as Response);

    const result = await updateVoiceSettings({
      provider: 'elevenlabs',
      api_key: 'sk_test_12345555',
      voice_id: 'custom-voice-id',
      model_id: 'eleven_multilingual_v2',
      stability: 0.7,
      similarity_boost: 0.85,
      style: 0.15,
      speed: 1.2,
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const callArgs = fetchSpy.mock.calls[0];
    expect(callArgs[0]).toContain('/v1/speech/voice-settings');
    const sentBody = JSON.parse((callArgs[1] as RequestInit).body as string);
    expect(sentBody.provider).toBe('elevenlabs');
    expect(sentBody.api_key).toBe('sk_test_12345555');
    expect(result.provider).toBe('elevenlabs');
    expect(result.masked_api_key).toBe('••••••••5555');
  });

  it('updateVoiceSettings throws sanitized error when request fails', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: false,
      status: 422,
      json: async () => ({ detail: 'Invalid voice provider' }),
    } as unknown as Response);

    await expect(updateVoiceSettings({ provider: 'invalid_prov' })).rejects.toThrow(
      'Invalid voice provider',
    );
  });

  it('testElevenLabsConnection returns connection status', async () => {
    const mockTestSuccess = {
      valid: true,
      status: 'connected',
      message: 'Successfully connected. Found 5 voices and 2 models.',
      voices_count: 5,
      models_count: 2,
    };

    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => mockTestSuccess,
    } as unknown as Response);

    const result = await testElevenLabsConnection('test-api-key');
    expect(result.valid).toBe(true);
    expect(result.status).toBe('connected');
    expect(result.voices_count).toBe(5);
  });

  it('fetchElevenLabsVoices returns parsed voice array', async () => {
    const mockVoices = {
      voices: [
        { voice_id: 'v1', name: 'Adam', category: 'premade' },
        { voice_id: 'v2', name: 'Bella', category: 'cloned' },
      ],
    };

    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => mockVoices,
    } as unknown as Response);

    const voices = await fetchElevenLabsVoices();
    expect(voices.length).toBe(2);
    expect(voices[0].voice_id).toBe('v1');
    expect(voices[0].name).toBe('Adam');
  });

  it('fetchElevenLabsModels returns TTS-compatible models', async () => {
    const mockModels = {
      models: [
        { model_id: 'eleven_turbo_v2_5', name: 'Eleven Turbo v2.5' },
        { model_id: 'eleven_multilingual_v2', name: 'Eleven Multilingual v2' },
      ],
    };

    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => mockModels,
    } as unknown as Response);

    const models = await fetchElevenLabsModels();
    expect(models.length).toBe(2);
    expect(models[0].model_id).toBe('eleven_turbo_v2_5');
  });

  it('previewElevenLabsVoice requests audio preview and returns Blob', async () => {
    const fakeBlob = new Blob(['fake-audio-content'], { type: 'audio/mpeg' });

    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      blob: async () => fakeBlob,
    } as unknown as Response);

    const blob = await previewElevenLabsVoice({
      voiceId: 'JBFqnCBsd6RMkjVDRZzb',
      modelId: 'eleven_turbo_v2_5',
      text: 'Preview phrase test.',
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const callArgs = fetchSpy.mock.calls[0];
    expect(callArgs[0]).toContain('/v1/speech/elevenlabs/preview');
    expect(blob.type).toBe('audio/mpeg');
  });

  it('provider switching can revert back to system provider safely', async () => {
    const revertResponse = {
      provider: 'system',
      voice_id: 'JBFqnCBsd6RMkjVDRZzb',
      model_id: 'eleven_turbo_v2_5',
      stability: 0.5,
      similarity_boost: 0.75,
      style: 0.0,
      speed: 1.0,
      has_api_key: true,
      masked_api_key: '••••••••1234',
    };

    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => revertResponse,
    } as unknown as Response);

    const result = await updateVoiceSettings({ provider: 'system' });
    expect(result.provider).toBe('system');
  });
});
