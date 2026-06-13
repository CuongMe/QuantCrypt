from __future__ import annotations

import hashlib
import re
from typing import Protocol

import numpy


class EmbeddingModel(Protocol):
    dimension: int

    def embed_texts(self, texts: list[str]) -> numpy.ndarray:
        ...


class HashEmbeddingModel:
    def __init__(self, dimension: int = 256) -> None:
        self.dimension = dimension
        self._token_pattern = re.compile(r"[A-Za-z0-9_]+")

    def embed_texts(self, texts: list[str]) -> numpy.ndarray:
        matrix = numpy.zeros((len(texts), self.dimension), dtype="float32")
        for row_index, text in enumerate(texts):
            tokens = self._token_pattern.findall(text.lower())
            if not tokens:
                continue
            for token in tokens:
                digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
                column_index = int.from_bytes(digest[:4], "little") % self.dimension
                sign = -1.0 if digest[4] & 1 else 1.0
                matrix[row_index, column_index] += sign
            norm = numpy.linalg.norm(matrix[row_index])
            if norm > 0:
                matrix[row_index] /= norm
        return matrix

