import random

def generate_random_name():
    first_name_size = random.randint(5, 8)
    last_name_size = random.randint(3, 8)

    first_name = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=first_name_size))
    last_name = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=last_name_size))

    return [first_name, last_name]

def generate_name_from_parents(parent1, parent2):
    first_name = random.choice([parent1.name[0], parent2.name[0]])
    last_name = random.choice([parent1.name[1], parent2.name[1]])
    return [first_name, last_name]


# Example usage
if __name__ == "__main__":
    for _ in range(5):
        print(generate_random_name())

