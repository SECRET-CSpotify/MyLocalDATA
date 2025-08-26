# hash_passwords.py
from streamlit_authenticator.utilities import Hasher

# Lista de contraseñas en texto plano
passwords = [
    "5{£g;My$985j",   # para admin
    "udJ_)l2*72Jo",   # para Andres Paz
    "`89eJ£sk57T$",   # para Laura Peña
    "Ic{99jaW4TW2",     # para David Gaviria
    "=C6Z94!iP6Nu",   # para Sergio Martinez
    "7,zYX;c6jl3G"    # para Stefany Espitia
]

# Generar hashes para cada contraseña
hashes = [Hasher.hash(pwd) for pwd in passwords]

# Mostrar en consola
for pwd, h in zip(passwords, hashes):
    print(f"{pwd} → {h}")
