from .brain_base import Brain

class SimpleBrain(Brain):
    def remember(self, key, value):
        self.memory[key] = value

    def recall(self, key):
        return self.memory.get(key, None)

    def think(self, thought):
        self.thoughts.append(thought)