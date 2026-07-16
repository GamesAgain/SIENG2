from abc import ABC, abstractmethod
import numpy as np

class BaseAttack(ABC):
    name: str = "base"

    @abstractmethod
    def analyze_blind(self, data_array: np.ndarray) -> dict:
        """
        Run statistical analysis on a single file (blind steganalysis).
        Returns a dict with detection results.
        """
        pass

