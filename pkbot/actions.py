'''
The actions that the player is allowed to take.
'''
from collections import namedtuple

ActionFold = namedtuple('ActionFold', [])
ActionCall = namedtuple('ActionCall', [])
ActionCheck = namedtuple('ActionCheck', [])
# Bet & Raise is dont throuhg same action.
ActionRaise = namedtuple('ActionRaise', ['amount'])
ActionBid = namedtuple('ActionBid', ['amount'])