# The CountryBase class serves as a foundational class for all countries in the simulation. 
# It contains common attributes such as name, area, and various ratings for healthcare, education, economy, and culture.
# Additionally, it has dictionaries to store regulations and resources specific to each country.

class Country:
    def __init__(self, name, area, start_population=0, healthcare_rating=0, education_rating=0, economy_rating=0, culture_rating=0, regulations=None, resources=None):
        self.name = name
        self.area = area
        self.start_population = start_population
        self.population = 0
        self.healthcare_rating = healthcare_rating
        self.education_rating = education_rating
        self.economy_rating = economy_rating
        self.culture_rating = culture_rating
        self.regulations = regulations if regulations is not None else {}
        self.resources = resources if resources is not None else {}
    
    def increase_healthcare_rating(self, rating):
        self.healthcare_rating += rating
    
    def get_healthcare_rating(self):
        return self.healthcare_rating
    
    def increase_education_rating(self, rating):
        self.education_rating += rating

    def get_education_rating(self):
        return self.education_rating
    
    def increase_economy_rating(self, rating):
        self.economy_rating += rating
    
    def get_economy_rating(self):
        return self.economy_rating
    
    def increase_culture_rating(self, rating):
        self.culture_rating += rating
    
    def get_culture_rating(self):
        return self.culture_rating

    def add_regulation(self, regulation_name, details):
        self.regulations[regulation_name] = details

    def get_regulation(self, regulation_name):
        return self.regulations.get(regulation_name, None)

    def add_resource(self, resource_name, quantity):
        self.resources[resource_name] = quantity
    
    def get_resource(self, resource_name):
        return self.resources.get(resource_name, None)



    
