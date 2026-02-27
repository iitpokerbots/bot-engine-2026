# PokerBot Template

This repository contains a minimal example poker bot written in Python.\
You can use this template to build your own bot for the competition.

The only file you **must** modify is `bot.py`. The only functions needed to be written by you are

``` python
on_hand_start(self, game_info, current_state, active)
on_hand_end(self, game_info, current_state, active)
get_move(self, game_info, current_state, active)
```

------------------------------------------------------------------------

# Running Your Bots

Run the following command to make two of your bots play a match. 

``` bash
python engine.py
```

They are instantiated from the files specified in `config.py`. Their names are also taken from the same file.

For example,
```python
BOT_1_NAME = 'BotA'
BOT_1_FILE = './example_bot.py'

BOT_2_NAME = 'BotB'
BOT_2_FILE= './example_bot.py'
```
With the above config, the bots are both instantiated using the algorithms specified in `./example_bot.py` and named `BotA` and `BotB`.

------------------------------------------------------------------------

# How the Bot Works

The game engine calls three important methods:

## `on_hand_start(...)`

Called at the beginning of every round.

You can use this to, for example, reset pre-hand variables or to change behaviour with round number.

The arguments are `game_info : GameInfo` and `current_state: PokerState`.

Information from these arguments can be used to make decisions at this point of time. For example, one can use `current_state.my_hand` to get their cards for this round, which may be used to calculate the preflop probability of winning this round.

This function does not return anything.

------------------------------------------------------------------------

## `on_hand_end(...)`

Called when the round finishes.

You can use this to, for example, incorporate changes to your strategy based on the result of the round. At this point, you can learn the opponent's revealed cards and wager, and use this information to understand opponent's behaviour and incorporate it into your strategy.

The arguments are `game_info : GameInfo` and `current_state: PokerState`.

As in `on_hand_start(...)`, the methods of these argument objects can be used in the function.

This function does not return anything.

------------------------------------------------------------------------

## `get_move(...)` (Most Important)

This function is called whenever the engine needs your action. This is where your strategy lives!

The arguments are `game_info : GameInfo` and `current_state: PokerState`.

This function is called whenever it is your turn in the game and an action is expected from you. One of the available action classes need to be returned.

You must return one of:

``` python
ActionFold()            # Fold
ActionCall()            # Call
ActionCheck()           # Check
ActionRaise(amount)     # Raise to amount
ActionBid(amount)       # Bid amount for auction
```

The auction logic of your strategy needs to be written in this function, for example:

```python
if current_state.street == 'auction':
    return ActionBid(max(10, current_state.my_chips)) # always bid 10
```

A very simple example strategy is:

``` python
if current_state.street == 'auction':
    return ActionBid(max(10, current_state.my_chips)) # always bid 10 chips for the auction if possible

if current_state.can_act(ActionCheck):  # check-call
    return ActionCheck()

if current_state.can_act(ActionCall):
    return ActionCall()

return ActionFold()
```

### Legal Actions

Always check what actions are allowed:

``` python
valid_actions = current_state.legal_actions # set of legal actions
```

Example:

``` python
if current_state.can_act(ActionRaise):  # this function checks if ActionRaise is in the set current_state.valid_actions
    min_raise, max_raise = current_state.get_raise_limits()
    return ActionRaise(min_raise)
```

Never attempt an invalid action --- the engine detects it and considers your bot's action as folding.

------------------------------------------------------------------------

# Understanding the Different Objects

## GameInfo

```python
game_info.bankroll      # the total number of chips you've gained or lost from the beginning of the game to the start of this round
game_info.time_bank     # the total number of seconds your bot has left to play this game
game_info.round_num     # the round number from 1 to NUM_ROUNDS
```

## `PokerState`

``` python
state.is_terminal       # true when the round has ended, false otherwise : true only in the input state to on_round_end(...)
state.street            # ongoing street : pre-flop, flop, auction, turn, or river respectively
state.my_hand           # your cards
state.board             # board cards
state.opp_revealed_hands    # opponent's  revealed cards or [] if nothing is revealed yet
state.my_chips          # the number of chips you have remaining
state.opp_chips         # the number of chips your opponent has remaining
state.my_wager          # the number of chips you have contributed to the pot this round of betting
state.opp_wager         # the number of chips your opponent has contributed to the pot this round of betting
state.pot               # total number of chips in the pot
state.cost_to_call      # difference between the opponent's wage and my wage when ActionCall is a legal action
state.is_bb             # true if you are the big blind of this round
state.legal_actions     # list of actions that can be taken by you at your turn
state.payoff            # your payoff for this round: is non zero only at the end of the round, when self.is_terminal == true
state.raise_bounds      # a tuple with the minimum and maximum allowed raises

state.can_act(action_class)   # true if you are allowed to take the action action_class
```

### Streets and Cards

Streets are denoted by strings in this system. The different possible streets are `preflop`, `flop`, `auction`, `turn`, and `river`. The current street can be accessed via `current_state.street`.

Every card is represented by a two character string. The first character is from the set {2, 3, 4, 5, 6, 7, 8, 9, T, J, Q, K} representing the value of the card and denoting 2, 3, 4, 5, 6, 7, 8, 9, 10, Jack, Queen and King, respectively. The second character is from the set {d, s, c, h} representing the suit of the card and denoting Diamonds, Spades, Clubs and Hearts, respectively.

For example, 'Ad' denotes the ace of diamonds, '5s' denotes 5 of spades.

------------------------------------------------------------------------

# Time Management


There are limits on the response time of your bot. Be very careful to write bots that respect these time limits. If your bot violates any of the two below time constraints, then it automatically looses the round (and any subsequent rounds in case the 20 seconds limit is breached)
- Every time the engine queries the bot, it gets 2 seconds to respond.
- The total response time (summation of response times of all queries in a match) is limited to 20 seconds.

Avoid heavy computation every action unless necessary.

``` python
game_info.time_bank     # the total number of seconds your bot has left to play this game
```

------------------------------------------------------------------------

# Tracking Opponent Behavior

You may want to write a bot that adapts to opponent's play style. For this purpose, you can track your opponent's behaviour. You can store class variables, for example,

``` python
self.opp_fold_count     # number of times opponent folded
self.opp_raise_count    # number of times opponent raised
```

and update them in `on_hand_end()` to adapt dynamically.

------------------------------------------------------------------------

# Logs

You can add `print` statements in your bot code for debugging. The printed lines appear in `<GAME_LOG_FOLDER>/<BOT_NAME>.plog`. GAME_LOG_FOLDER and BOT_NAME are to be specified in `config.py`.

Moreover, whenever a match is played, the actions of the bot and the entire sequence of events in the match are stored in the game log which is found in the timestamped file `<GAME_LOG_FOLDER><timestamp>.glog`. The timestamp denotes the time at the start of the game. The game log can also be useful in debugging.

------------------------------------------------------------------------

# Important Rules

-   Do NOT modify engine files.
-   Always return a valid action.
-   Do not exceed time limits.
-   Most importantly, have fun developing your bots! Good Luck!
