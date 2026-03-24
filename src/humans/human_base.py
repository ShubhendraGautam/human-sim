import asyncio
import time

from src.brains import SimpleBrain

class Human:
    def __init__(self, gender, first_name, last_name, is_first_generation, country):
        self.first_name = first_name
        self.last_name = last_name
        self.gender = gender
        self.time_of_birth = time.time()
        self.health = 100
        self.happiness = 100
        self.education = 0
        self.wealth = 0
        self.abilities = {}
        self.brain = SimpleBrain()
        self.coordinates = (0, 0)
        self.country = country
        self.is_first_generation = is_first_generation
        
    def get_age(self):
        if self.is_first_generation:
            return  ((time.time() - self.time_of_birth) // 600) + 20  # First generation starts at age 20
        # Each 10 min is 1 year in human life
        return (time.time() - self.time_of_birth) // 600
