from abc import ABC, abstractmethod

class Brain(ABC):
    def __init__(self):
        self.memory = {}
        self.thoughts = []

    @abstractmethod
    def remember(self, key, value):
        pass

    @abstractmethod
    def recall(self, key):
        pass

    @abstractmethod
    def think(self, thought):
        pass
