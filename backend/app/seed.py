from .db import SessionLocal
from .catalogue import seed_catalogue
def main():
    with SessionLocal() as db: print(seed_catalogue(db))
if __name__=="__main__": main()
