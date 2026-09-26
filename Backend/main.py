"""
Todo:


"""

# import os
from dotenv import load_dotenv
from flask import Flask, request
load_dotenv()

# print(os.getenv(""))

app = Flask(__name__)

@app.route('/')
def hello():
    return 'Hello, World!'

# Dashboard
@app.route('/dashboard')
def dashboard():
    return 'Dashboard Page (homepage)'

# Report
@app.route('/report')
def report():
    return 'Report Page (Big circle)'

# Search
@app.route('/search')
def search():
    sex=request.args.get('sex')
    testlist = request.args.to_dict(flat=False)
    print(testlist)
    return f'Search Page for {sex}'

# Advanced Search
@app.route('/advanced-search')
def advanced_search():
    return 'Advanced Search Page'
