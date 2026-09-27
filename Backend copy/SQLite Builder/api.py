# import os
from dotenv import load_dotenv
from flask import Flask, jsonify, request
load_dotenv()

import db
import validation

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

@app.route('/truncated_search')
def truncared_search():
    con = db.connect()
    try:
        params = 

# Search
@app.route('/search')
def search():
    con = db.connect()
    try:
        params = validation.process_search_query(request.args)
    except validation.QueryError as exc:
        con.close()
        return jsonify({"error": {"code": "bad_request", "message": str(exc), "details": exc.errors}}), 400
    try:
        studies, total = db.search(con, **params, limit=10)
        return jsonify({"studies": studies, "total": total})
    finally:
        con.close()



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)