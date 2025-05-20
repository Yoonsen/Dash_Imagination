from flask import Flask
from flask_cors import CORS, cross_origin

app = Flask(__name__)
CORS(app)



@app.route('/helloworld/')
@cross_origin()
def hello():
    return "Hello World!"

if __name__ == '__main__':
   app.run(host='0.0.0.0', port=8050)