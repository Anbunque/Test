import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from datetime import datetime
from pymongo import MongoClient
import threading
import time

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Used for session management

# MongoDB connection setup
mongo_uri = os.getenv("MONGO_URI")
client = MongoClient(mongo_uri)  # Replace with your actual MongoDB connection string
db = client.get_database('library')  # Access the library database
books_collection = db['books'] 
lend_collection = db['lend'] 


# Method to reload books from MongoDB
def reload_books():
    global Benlib
    Benlib.booklist = []  # Clear the existing list
    books_from_db = books_collection.find()  # Fetch the updated books from MongoDB
    for book in books_from_db:
        Benlib.booklist.append(book)
        
# Reconnect to MongoDB every 30 seconds
def restart_mongo_connection():
    global client, db, books_collection, lend_collection
    while True:
        time.sleep(5)
        print("Restarting MongoDB connection...")
        # Re-initialize MongoDB client
        client = MongoClient("mongodb+srv://anbumani:Anbu007@cluster0.poivzxq.mongodb.net/")  # Replace with your actual MongoDB connection string
        db = client.get_database('library')  # Access the library database
        books_collection = db['books']
        lend_collection = db['lend']
        print("MongoDB connection restarted.")

# Start the background thread to restart MongoDB connection
thread = threading.Thread(target=restart_mongo_connection)
thread.daemon = True
thread.start()

class Library:
    def __init__(self, books, name):
        self.booklist = books  # A list of dictionaries containing book details
        self.name = name
        self.lenDict = {}
        self.lent_books_collection = db.lent_books  # Collection for lent books

    def displayBooks(self):
        return self.booklist

    def lendBook(self, book_title, borrower_name):
        for book in self.booklist:
            if book['title'] == book_title and book['available']:
                book['available'] = False
                self.lenDict[book_title] = borrower_name

                books_collection.update_one(
                    {'title': book_title}, 
                    {'$set': {'available': False, 'borrower': borrower_name}},
                    upsert=False
                )
                self.lent_books_collection.insert_one({
                    'title': book_title,
                    'borrower': borrower_name,
                    'lend_date': datetime.now()
                })
                return f'Book "{book_title}" has been lent to {borrower_name}.'
        return 'This book is either already lent out or unavailable.'

    def returnBook(self, book_title):
        if book_title in self.lenDict:
            del self.lenDict[book_title]  # Remove from lent list
            for book in self.booklist:
                if book['title'] == book_title:
                    book['available'] = True

            books_collection.update_one(
                {'title': book_title}, 
                {'$set': {'available': True, 'borrower': None}},
                upsert=False
            )
            self.lent_books_collection.delete_one({'title': book_title})
            return f'Book "{book_title}" has been returned.'
        return 'This book was not lent.'


    def addBook(self, book):
        self.booklist.append(book)
        books_collection.insert_one(book)
        return f"The book '{book['title']}' has been added to the library."


# Initialize the library
Benlib = Library([], 'Our Library')

# Load books from MongoDB when the app starts
def load_books():
    books_from_db = books_collection.find()
    for book in books_from_db:
        Benlib.booklist.append(book)

load_books()

@app.route('/')
def home():
    reload_books()  # Reload books from DB
    available_books = [book['title'] for book in Benlib.booklist if book['available']]
    lent_books = [book['title'] for book in Benlib.booklist if not book['available']]
    return render_template('index.html', library=Benlib, available_books=available_books, lent_books=lent_books)



@app.route('/display', methods=['GET'])
def display_books():
    genre = request.args.get('genre')
    search_query = request.args.get('search')

    if genre:
        books = [book for book in Benlib.booklist if book['genre'] == genre]
    else:
        books = Benlib.booklist 

    if search_query:
        books = [book for book in books if search_query.lower() in book['title'].lower()]

    for book in books:
        lent_entry = lend_collection.find_one({'book': book['title'], 'status': 'lent'})
        if lent_entry:
            book['status'] = f"Lent to: {lent_entry['borrower']}"
        else:
            book['status'] = 'Available to lend'

    return render_template('display_books.html', books=books, library=Benlib, search_query=search_query)

@app.route('/lend', methods=['POST'])
def lend_book():
    book_name = request.form['book']
    borrower_name = request.form['name']

    book = books_collection.find_one({'title': book_name, 'available': True})

    if not book:
        flash('This book is not available for lending.', 'error')
        return redirect(url_for('home'))

    # Lend the book
    books_collection.update_one(
        {'title': book_name},
        {'$set': {'available': False, 'borrower': borrower_name}}
    )

    lend_collection.insert_one({
        'book': book_name,
        'borrower': borrower_name,
        'status': 'lent'
    })

    flash(f'{borrower_name} has successfully lent the book: {book_name}')
    
    # Reload the books
    reload_books()

    # Fetch the latest available and lent books
    available_books = [book['title'] for book in Benlib.booklist if book['available']]
    lent_books = [book['title'] for book in Benlib.booklist if not book['available']]

    return render_template('index.html', available_books=available_books, lent_books=lent_books, library=Benlib)


@app.route('/return', methods=['POST'])
def return_book():
    book_name = request.form['book']

    lend_collection.delete_one({'book': book_name, 'status': 'lent'})

    books_collection.update_one(
        {'title': book_name},
        {'$set': {'available': True, 'borrower': None}}
    )

    flash(f'Book "{book_name}" returned successfully!')

    # Reload the books
    reload_books()

    # Fetch the latest available and lent books
    available_books = [book['title'] for book in Benlib.booklist if book['available']]
    lent_books = [book['title'] for book in Benlib.booklist if not book['available']]

    return render_template('index.html', available_books=available_books, lent_books=lent_books, library=Benlib)



ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "p"

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            message = "Invalid credentials. Please try again."
            return render_template('admin_login.html', message=message)
    return render_template('admin_login.html')

@app.route('/admin/dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    
    if request.method == 'POST':
        title = request.form['title']
        author = request.form['author']
        edition = request.form['edition']
        available = request.form['available'] == 'True'

        new_book = {
            'title': title,
            'author': author,
            'edition': edition,
            'available': available,
        }

        message = Benlib.addBook(new_book)
        flash(message)
        return redirect(url_for('admin_dashboard'))
    
    return render_template('admin_dashboard.html', library=Benlib)

@app.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)
