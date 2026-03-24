import random

# This script generates random metadata for countries.
# name - A random string of uppercase letters, length between 5 and 15.
# population - A random integer between 100 and 1000.
# area - A random integer between 10,000 and 10,000,000.
# healthcare_rating, education_rating, economy_rating, culture_rating - Random integers between 1 and 10.

MIN_NAME_LENGTH = 5
MAX_NAME_LENGTH = 15
MIN_POPULATION = 1
MAX_POPULATION = 10
MIN_AREA = 10_000
MAX_AREA = 10_000_000
MIN_RATING = 1
MAX_RATING = 10

def generate_random_country_metadata():

    country_name_len = random.randint(MIN_NAME_LENGTH, MAX_NAME_LENGTH)
    country_name = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=country_name_len))
    
    population = random.randint(MIN_POPULATION, MAX_POPULATION)
    area = random.randint(MIN_AREA, MAX_AREA)
    healthcare_rating = random.randint(MIN_RATING, MAX_RATING)
    education_rating = random.randint(MIN_RATING, MAX_RATING)
    economy_rating = random.randint(MIN_RATING, MAX_RATING)
    culture_rating = random.randint(MIN_RATING, MAX_RATING)

    return {
        "name": country_name,
        "start_population": population,
        "area": area,
        "healthcare_rating": healthcare_rating,
        "education_rating": education_rating,
        "economy_rating": economy_rating,
        "culture_rating": culture_rating
    }
        