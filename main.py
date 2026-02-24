from fastapi import FastAPI

# This creates your app
app = FastAPI()

# This is a Layer 1 "Exposer" (An API Endpoint)
@app.get("/")
def read_root():
    return {"message": "Hello Cavengers! The Backend is alive!"}