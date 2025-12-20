from werkzeug.security import generate_password_hash

hashed_pw = generate_password_hash('Xyz@1234')
print(hashed_pw)
