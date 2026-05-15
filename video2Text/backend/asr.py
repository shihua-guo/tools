import sherpa_onnx
import os
from pathlib import Path
import logging
import wave
import numpy as np

class ASRProcessor:
    def __init__(self, model_dir: str, punc_dir: str):
        self.model_dir = Path(model_dir)
        self.punc_dir = Path(punc_dir)
        
        # Configure ASR
        self.recognizer = sherpa_onnx.OfflineRecognizer.from_paraformer(
            paraformer=str(self.model_dir / "model.int8.onnx"),
            tokens=str(self.model_dir / "tokens.txt"),
            num_threads=4,
            sample_rate=16000,
            feature_dim=80,
            decoding_method="greedy_search",
            debug=False
        )
        
        # Punctuation is temporarily disabled due to sherpa_onnx model compatibility
        # (current ct-transformer model metadata is incompatible with installed runtime).
        self.punc = None
        logging.warning("Punctuation disabled: incompatible punctuation model/runtime")

    def process(self, audio_path: str) -> str:
        s = self.recognizer.create_stream()

        # sherpa_onnx>=1.12 removed accept_wave_file; feed waveform directly
        with wave.open(audio_path, "rb") as wf:
            sample_rate = wf.getframerate()
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            frames = wf.readframes(wf.getnframes())

        if sampwidth != 2:
            raise RuntimeError(f"Unsupported sample width: {sampwidth} bytes")

        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        if n_channels > 1:
            audio = audio.reshape(-1, n_channels).mean(axis=1)

        s.accept_waveform(sample_rate, audio)
        self.recognizer.decode_stream(s)
        text = s.result.text

        # Add punctuation if available
        if self.punc is not None:
            return self.punc.add_punctuation(text)
        return text

# Usage:
# processor = ASRProcessor("./models/paraformer-offline-zh", "./models/punc_ct-transformer_cn-en")
# print(processor.process("test.wav"))
