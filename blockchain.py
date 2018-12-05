"""
Created by Alexander Swanson on 12/01/18.
Copyright (c) 2018, Alexander Joseph Swanson Villares
alexjosephswanson@gmail.com

Resource: https://hackernoon.com/learn-blockchains-by-building-one-117428612f46
"""

import hashlib
import json
from textwrap import dedent
from time import time
from uuid import uuid4

from flask import Flask, jsonify, request
from urllib.parse import urlparse
import requests


class Blockchain(object):

    def __init__(self):

        self.chain = []
        self.current_transactions = []

        self.nodes = set()

        # Create the genesis block.
        self.new_block(previous_hash=1, proof=100)

    def valid_chain(self, chain):
        """
        Determine if a given blockchain is valid. Consensus is achieved by comparing a blockchain to the longest
        blockchain in the verified network.

        :param chain: <list> A blockchain
        :return: <bool> True if valid, False if not
        """

        last_block = chain[0]
        current_index = 1

        while current_index < len(chain):

            block = chain[current_index]
            print(f'{last_block}')
            print(f'{block}')
            print("\n-----------\n")

            # Check that the hash of the block is correct.
            if block['previous_hash'] != self.hash(last_block):
                return False

            # Check that the proof of work is correct.
            if not self.valid_proof(last_block['previous_hash'], block['proof']):
                return False

            last_block = block
            current_index += 1

        return True

    def resolve_conflicts(self):
        """
        This is the Consensus Algorithm, it resolves conflicts
        by replacing the chain with the longest one in the network.

        :return: <bool> True if the chain was replaced, False if not.
        """

        neighbours = self.nodes
        new_chain = None
        max_chain_length = len(self.chain)

        # Grab and verify the chains from all the nodes in the network.
        for node in neighbours:

            response = requests.get(f'http://{node}/chain')

            if response.status_code == 200:
                length = response.json()['length']
                chain = response.json()['chain']

                # Check if the length is longer and the chain is valid.
                if length > max_chain_length and self.valid_chain(chain):
                    max_chain_length = length
                    new_chain = chain

        # Replace the chain if a new one was discovered and validated.
        if new_chain:
            self.chain = new_chain
            return True

        return False

    def register_node(self, address):
        """
        Add a new node to the list of nodes

        :param address: <str> Address of node. Eg. 'http://192.168.0.5:5000'.
        :return: None.
        """

        parsed_url = urlparse(address)
        self.nodes.add(parsed_url.netloc)

    def new_block(self, previous_hash, proof):
        """
        Creates a new Block in the Blockchain.

        :param proof: <int> The proof given by the Proof of Work algorithm.
        :param previous_hash: (Optional) <str> Hash of previous Block.
        :return: <dict> New Block.
        """

        block = {
            'index': len(self.chain) + 1,
            'timestamp': time(),
            'transactions': self.current_transactions,
            'proof': proof,
            'previous_hash': previous_hash or self.hash(self.chain[-1])
        }

        # Reset the current list of transactions.
        self.current_transactions = []

        self.chain.append(block)
        return block

    def new_transaction(self, sender, recipient, amount):
        """
        Adds a new transaction to the list of transactions.

        :param sender: <str> Address of the Sender.
        :param recipient: <str> Address of the Recipient.
        :param amount: <int> Amount of the transaction.
        :return: <int> The index of the Block that will hold this transaction.
        """

        self.current_transactions.append({
            'sender': sender,
            'recipient': recipient,
            'amount': amount,
        })

        return self.last_block['index'] + 1

    def proof_of_work(self, last_proof):
        """
        Simple Proof of Work Algorithm:
         - Find a number p' such that hash(pp') contains leading 4 zeroes, where p is the previous p'
         - p is the previous proof, and p' is the new proof
        :param last_proof: <int>
        :return: <int>
        """

        proof = 0
        while self.valid_proof(last_proof, proof) is False:
            proof += 1

        return proof

    @staticmethod
    def valid_proof(last_proof, proof):
        """
        Validates the Proof: Does hash(last_proof, proof) contain 4 leading zeroes?

        :param last_proof: <int> Previous Proof.
        :param proof: <int> Current Proof.
        :return: <bool> True if correct, False if not.
        """

        guess = f'{last_proof}{proof}'.encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:4] == "0000"

    @staticmethod
    def hash(block):
        """
        Creates a SHA-256 hash of a Block.

        :param block: <dict> The Block.
        :return: <str> The hash.
        """

        block_string = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    @property
    def last_block(self):
        """
        Returns the last block in the chain.

        :return:
        """
        return self.chain[-1]


# Instantiate the node.
app = Flask(__name__)

# Generate a globally unique address for this node.
node_identifier = str(uuid4()).replace('-', '')

# Instantiate the Blockchain.
blockchain = Blockchain()


@app.route('/chain', methods=['GET'])
def full_chain():
    response = {
        'chain': blockchain.chain,
        'length': len(blockchain.chain),
    }

    return jsonify(response), 200


@app.route('/transactions/new', methods=['POST'])
def new_transaction():
    values = request.get_json()

    # Check that the required fields are in the POST'ed data
    required = ['sender', 'recipient', 'amount']
    if not all(k in values for k in required):
        return 'Missing values', 400

    # Create a new transaction.
    index = blockchain.new_transaction(values['sender'], values['recipient'], values['amount'])

    response = {'message': f'Transaction will be added to Block {index}'}

    return jsonify(response), 201


@app.route('/mine', methods=['GET'])
def mine():
    """
    Mines a new block in the chain.

    :return: The updated chain and its new block.
    """

    # We run the proof of work algorithm to get the next proof...
    last_block = blockchain.last_block
    last_proof = last_block['proof']
    proof = blockchain.proof_of_work(last_proof)

    # We must receive a reward for finding the proof.
    # The sender is "0" to signify that this node has mined a new coin.
    blockchain.new_transaction(
        sender="0",
        recipient=node_identifier,
        amount=1,
    )

    # Forge the new Block and add it to the Chain.
    previous_hash = blockchain.hash(last_block)
    block = blockchain.new_block(proof, previous_hash)

    response = {
        'message': "New Block forged.",
        'index': block['index'],
        'transactions': block['transactions'],
        'proof': block['proof'],
        'previous_hash': block['previous_hash'],
    }

    return jsonify(response), 200


@app.route('/nodes/register', methods=['POST'])
def register_nodes():
    """
    Registers a list of new nodes.

    :return: The new listing of nodes or an error message indicating that an invalid list of nodes was submitted.
    """

    # Get the Blockchain data.
    values = request.get_json()

    # Get a list of the nodes on the main network.
    nodes = values.get('nodes')

    # Indicate possible error.
    if nodes is None:
        return "Error: Please supply a valid list of nodes", 400

    # Register the new nodes.
    for node in nodes:
        blockchain.register_node(node)

    response = {
        'message': 'New nodes have been added',
        'total_nodes': list(blockchain.nodes),
    }

    return jsonify(response), 201


@app.route('/nodes/resolve', methods=['GET'])
def consensus():
    """
    Implements the consensus algorithm, updating the main Blockchain if it was found to have been updated.

    :return: The new or current Blockchain.
    """

    # Attempt to resolve any conflicts.
    replaced = blockchain.resolve_conflicts()

    # Return the new Blockchain if the old one was replaced.
    if replaced:
        response = {
            'message': 'Our chain was replaced',
            'new_chain': blockchain.chain
        }

    else:
        response = {
            'message': 'The main chain is authoritative',
            'chain': blockchain.chain
        }

    return jsonify(response), 200



def __run__(port):
    app.run(host='0.0.0.0', port=port)

__run__(5000)