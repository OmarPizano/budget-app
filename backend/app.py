from datetime import datetime
from flask import Flask, abort, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from os import getenv, name

from sqlalchemy import func

load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = getenv('DB_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
CORS(app)

db = SQLAlchemy(app)

# modelos
class Budget(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(256), nullable=False)
    max = db.Column(db.Integer, nullable=False)
    current = db.Column(db.Integer, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'max': self.max,
            'current': self.current,
        }

class Account(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(256), nullable=False)
    balance = db.Column(db.Integer, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'balance': self.balance
        }

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False, default=datetime.now())
    description = db.Column(db.String(256), nullable=False)
    type = db.Column(db.String(3), nullable=False)
    amount = db.Column(db.Integer, nullable=False)

    account_id = db.Column(db.Integer, db.ForeignKey(Account.id))
    budget_id = db.Column(db.Integer, db.ForeignKey(Budget.id), nullable=True)

    account = db.relationship('Account', foreign_keys=[account_id])
    budget = db.relationship('Budget', foreign_keys=[budget_id])

    def __init__(self, description, type, amount, account_id, budget_id=None):
        self.description = description
        self.type = type
        self.amount = amount
        self.account_id = account_id
        self.budget_id = budget_id
        self.date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')


    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date,
            'description': self.description,
            'type': self.type,
            'amount': self.amount,
            'account_name': self.account.name,
            'budget_name': self.budget.name if self.budget is not None else None
        }

with app.app_context():
    db.create_all()

# rutas
@app.route('/transactions', methods = ['GET'])
def transactions_get_all():
    transactions = Transaction.query.all()
    results = [transaction.to_dict() for transaction in transactions]
    return results, 200

@app.route('/transactions/<int:id>', methods = ['GET'])
def transactions_get_one(id):
    transaction = db.session.get(Transaction, id)
    if not transaction:
        abort(404)
    return transaction.to_dict(), 200

@app.route('/transactions', methods = ['POST'])
def transactions_create():
    data = request.get_json()
    # mandatory params
    expected_params = ['description', 'type', 'amount', 'account_id']
    for param in expected_params:
        if param not in data:
            abort(400)
    args = {
        'description': data['description'],
        'type': data['type'],
        'amount': data['amount'],
        'account_id': data['account_id'], 
    }
    # only ask for 'budget_id' when transaction type is 'out'
    if data['type'] == 'out':
        if 'budget_id' not in data:
            abort(400)
        else:
            args.update({'budget_id': data['budget_id']})
    # update related account/budget items
    account = db.session.get(Account, data['account_id'])
    if data['type'] == 'in':
        account.balance += data['amount']
    else:
        account.balance -= data['amount']
        budget = db.session.get(Budget, data['budget_id'])
        budget.current -= data['amount']
    # create transaction
    new_transaction = Transaction(**args)
    db.session.add(new_transaction)
    db.session.commit()
    return new_transaction.to_dict(), 201
    
@app.route('/transactions/<int:id>', methods = ['DELETE'])
def transactions_delete(id):
    transaction_to_delete = db.session.get(Transaction, id)
    if not transaction_to_delete:
        abort(404)
    # update related account/budget items
    account = db.session.get(Account, transaction_to_delete.account_id)
    if transaction_to_delete.type == 'in':
        account.balance -= transaction_to_delete.amount
    else:
        account.balance += transaction_to_delete.amount
        budget = db.session.get(Budget, transaction_to_delete.budget_id)
        budget.current += transaction_to_delete.amount
    # delete transaction
    db.session.delete(transaction_to_delete)
    db.session.commit()
    return {}, 204

@app.route('/transactions/<int:id>', methods = ['PATCH'])
def transactions_update(id):
    data = request.get_json()
    # optional params (`type` cannot be changed)
    optional_params = ['description', 'amount', 'account_id', 'budget_id']
    selected_params = []
    for param in optional_params:
        if param in data:
            selected_params.append(param)
    if len(selected_params) == 0:
        abort(400)
    transaction_to_update = db.session.get(Transaction, id)
    if not transaction_to_update:
        abort(404)
    if transaction_to_update.type == 'in':
        if 'budget_id' in data:
            abort(400)
    for param in selected_params:
        if param == 'description':
            transaction_to_update.description = data['description']
        elif param == 'amount':
            account = db.session.get(Account, transaction_to_update.account_id)
            if transaction_to_update.type == 'in':
                account.balance -= transaction_to_update.amount
                account.balance += data['amount']
            else:
                budget = db.session.get(Budget, transaction_to_update.budget_id)
                budget.current += transaction_to_update.amount
                budget.current -= data['amount']
                account.balance += transaction_to_update.amount
                account.balance -= data['amount']
            transaction_to_update.amount = data['amount']
        elif param == 'account_id':
            old_account = db.session.get(Account, transaction_to_update.account_id)
            new_account = db.session.get(Account, data['account_id'])
            if transaction_to_update.type == 'in':
                old_account.balance -= transaction_to_update.amount
                new_account.balance += transaction_to_update.amount
            if transaction_to_update.type == 'out':
                old_account.balance += transaction_to_update.amount
                new_account.balance -= transaction_to_update.amount
            transaction_to_update.account_id = data['account_id']
        elif param == 'budget_id':
            old_budget = db.session.get(Budget, transaction_to_update.budget_id)
            new_budget = db.session.get(Budget, data['budget_id'])
            old_budget.current += transaction_to_update.amount 
            new_budget.current -= transaction_to_update.amount 
            transaction_to_update.budget_id = data['budget_id']

    db.session.commit()
    return {}, 204

@app.route('/transactions/search/<string:pattern>', methods = ['GET'])
def names_search(pattern):
    transactions = db.session.query(Transaction).filter(func.lower(Transaction.description).contains(pattern.lower())).all()
    results = [transaction.to_dict() for transaction in transactions]
    return results, 200


@app.route('/accounts', methods = ['GET'])
def accounts_get_all():
    accounts = Account.query.all()
    results = [account.to_dict() for account in accounts]
    return results, 200

@app.route('/budgets', methods = ['GET'])
def budgets_get_all():
    budgets = Budget.query.all()
    results = [budget.to_dict() for budget in budgets]
    return results, 200

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
