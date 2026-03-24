from multiprocessing import Process
from src.countries import Country
from src.humans.human_base import Human
from time import sleep
from tools import generate_random_country_metadata
from tools import get_random_gender
from tools import generate_random_name

class CountrySim(Country):
    def __init__(self):
        country_metadata = generate_random_country_metadata()
        super().__init__(
            name=country_metadata["name"],
            area=country_metadata["area"],
            healthcare_rating=country_metadata["healthcare_rating"],
            education_rating=country_metadata["education_rating"],
            economy_rating=country_metadata["economy_rating"],
            culture_rating=country_metadata["culture_rating"],
            start_population=country_metadata["start_population"],
        )
    

class HumanSim(Human):
    def __init__(self):
        gender = get_random_gender()
        first_name, last_name = generate_random_name()
        super().__init__(gender=gender, first_name=first_name, last_name=last_name, is_first_generation=True, country=None)

def start_first_generation(country_name):
    human_sim = HumanSim()
    human_sim.country = country_name
    print(f"Simulating life for {human_sim.first_name} {human_sim.last_name} in {country_name}")
    # Simulate life events here (e.g., education, work, relationships)
    sleep(0.1)  # Simulate time passing for the human's life events

def run_simulation():
    country_sim = CountrySim()
    start_population = country_sim.start_population
    print(f"Starting simulation for {country_sim.name} with population {start_population}")

    for i in range(start_population):
        start_first_generation(country_sim.name)
        country_sim.population += 1
    
    

if __name__ == "__main__":
    run_simulation()