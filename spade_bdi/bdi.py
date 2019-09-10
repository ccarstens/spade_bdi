# -*- coding: utf-8 -*-
import asyncio
import time
from ast import literal_eval
from loguru import logger
from collections import deque
import agentspeak as asp
import agentspeak.runtime
from agentspeak.stdlib import actions as asp_action
from spade.behaviour import CyclicBehaviour
from spade.agent import Agent
from spade.template import Template
from spade.message import Message

import aioconsole

PERCEPT_TAG = frozenset([asp.Literal("source", (asp.Literal("percept"),))])


class BDIAgent(Agent):
    def __init__(self, jid: str, password: str, asl: str, actions=None, *args, **kwargs):
        self.asl_file = asl
        self.bdi_enabled = False
        self.bdi_intention_buffer = deque()
        self.bdi = None
        self.bdi_agent = None

        super().__init__(jid, password, *args, **kwargs)
        while not self.loop:
            time.sleep(0.01)

        self.bdi_env = asp.runtime.Environment()
        if isinstance(actions, asp.Actions):
            self.bdi_actions = actions
        else:
            self.bdi_actions = asp.Actions(asp_action)

        # self._load_asl()

    def pause_bdi(self):
        self.bdi_enabled = False

    def resume_bdi(self):
        self.bdi_enabled = True

    def add_behaviour(self, behaviour, template=None):
        if isinstance(behaviour, self.BDIBehaviour):
            self.bdi = behaviour
        super().add_behaviour(behaviour, template)

    def set_asl(self, asl_file: str):
        self.asl_file = asl_file
        self.load_asl()

    def load_asl(self):
        self.pause_bdi()
        try:
            with open(self.asl_file) as source:
                self.bdi_agent = self.bdi_env.build_agent(source, self.bdi_actions)
            self.bdi_agent.name = self.jid
            self.resume_bdi()
        except FileNotFoundError:
            logger.info("Warning: ASL specified for {} does not exist. Disabling BDI.".format(self.jid))
            self.asl_file = None
            self.pause_bdi()

    def on_start(self):
        self.load_asl()

    class BDIBehaviour(CyclicBehaviour):
        def __init__(self):
            super().__init__()
            self.custom_ilf_types = []

        def setup(self):
            """should be called AFTER the behaviour was added to an agent
                because otherwise the behaviour doesnt have an agent property"""
            self.add_actions()
            self.add_custom_actions()
            self.agent.load_asl()

        def add_actions(self):
            @self.agent.bdi_actions.add(".send", 3)
            def _send(agent, term, intention):

                receivers = asp.grounded(term.args[0], intention.scope)
                if isinstance(receivers, str) or isinstance(receivers, asp.Literal):
                    receivers = (receivers,)
                ilf = asp.grounded(term.args[1], intention.scope)
                if not asp.is_atom(ilf):
                    return
                ilf_type = ilf.functor
                mdata = {"performative": "BDI", "ilf_type": ilf_type, }
                for receiver in receivers:
                    body = asp.asl_str(asp.freeze(term.args[2], intention.scope, {}))
                    msg = Message(to=str(receiver), body=body, metadata=mdata)
                    self.agent.submit(self.send(msg))
                yield

            @self.agent.bdi_actions.add(".custom_action", 1)
            def _custom_action(agent, term, intention):
                asp.grounded(term.args[0], intention.scope)
                yield

            @self.agent.bdi_actions.add_function(".a_function", (int,))
            def _a_function(x):
                return x ** 4

            @self.agent.bdi_actions.add_function("literal_function", (asp.Literal,))
            def _literal_function(x):
                return x

        def add_custom_actions(self):
            """Override this method for registering your own actions and functions"""
            pass

        def set_singleton_belief(self, name: str, *args):
            """Set an agent's belief. If it already exists, updates it. This method removes all existing
                beliefs with the same functor and therefore only allows for one belief per functor"""
            new_args = ()
            for x in args:
                if type(x) == str:
                    new_args += (asp.Literal(x),)
                else:
                    new_args += (x,)

            term = asp.Literal(name, tuple(new_args), PERCEPT_TAG)
            found = False
            for belief in list(self.agent.bdi_agent.beliefs[term.literal_group()]):
                if asp.unifies(term, belief):
                    found = True
                else:
                    self.agent.bdi_intention_buffer.append((asp.Trigger.removal, asp.GoalType.belief, belief,
                                                            asp.runtime.Intention()))
            if not found:
                self.agent.bdi_intention_buffer.append((asp.Trigger.addition, asp.GoalType.belief, term,
                                                        asp.runtime.Intention()))


        def add_belief(self, name: str, *args, intention=asp.runtime.Intention(), source="percept"):
            """Adds additional belief literal, does not update existing ones"""

            trigger = asp.Trigger.addition
            goal_type = asp.GoalType.belief

            literal = get_literal_from_functor_and_arguments(name, args, intention=intention, source=source)

            self.agent.bdi_intention_buffer.append((trigger, goal_type, literal, intention))


        def remove_belief(self, functor: str, *args, source="percept"):
            """Remove an existing agent's belief."""

            trigger = asp.Trigger.removal
            goal_type = asp.GoalType.belief

            literal = get_literal_from_functor_and_arguments(functor, args)
            self.agent.bdi_intention_buffer.append((trigger, goal_type, literal, asp.runtime.Intention()))

        def get_belief_by_functor(self, key: str, source=False):
            """Get an agent's existing belief. The first belief matching
            <key> is returned. Keep <source> False to strip source."""
            key = str(key)
            for beliefs in self.agent.bdi_agent.beliefs:
                if beliefs[0] == key:
                    raw_belief = (str(list(self.agent.bdi_agent.beliefs[beliefs])[0]))
                    raw_belief = self._remove_source(raw_belief, source)
                    belief = raw_belief
                    return belief
            return None

        @staticmethod
        def _remove_source(belief, source):
            if ')[source' in belief and not source:
                belief = belief.split('[')[0].replace('"', '')
            return belief

        def get_belief_value(self, key: str):
            """Get an agent's existing value or values of the <key> belief. The first belief matching
            <key> is returned"""
            belief = self.get_belief_by_functor(key)
            if belief:
                return tuple(belief.split('(')[1].split(')')[0].split(','))
            else:
                return None

        def get_beliefs(self, source=False):
            """get all beliefs of an agent"""
            beliefs = []
            for belief_arity, belief_values in self.agent.bdi_agent.beliefs.items():
                for stored_belief in belief_values:
                    raw_belief = str(stored_belief)
                    raw_belief = self._remove_source(raw_belief, source)
                    beliefs.append(raw_belief)
            return beliefs

        def print_beliefs(self, source=False):
            """Print agent's beliefs.Keep <source> False to strip source."""
            for beliefs in self.agent.bdi_agent.beliefs.values():
                for belief in beliefs:
                    print(self._remove_source(str(belief), source))

        async def run(self):
            """
            Coroutine run cyclic.
            """
            if self.agent.bdi_enabled:
                msg = await self.receive(timeout=0)
                if msg:
                    mdata = msg.metadata
                    ilf_type = mdata["ilf_type"]
                    if ilf_type == "tell":
                        functor, arguments = parse_literal(msg.body)
                        self.add_belief(functor, *arguments, source=msg.sender)
                    elif ilf_type == "untell":
                        functor, arguments = parse_literal(msg.body)
                        self.remove_belief(functor, *arguments, source=msg.sender)
                    elif ilf_type == "achieve":
                        functor, arguments = parse_literal(msg.body)
                        self.add_achievement_goal(functor, *arguments, source=msg.sender)
                    elif ilf_type in self.custom_ilf_types:
                        await self.handle_message_with_custom_ilf_type(msg)
                    else:
                        raise asp.AslError("unknown illocutionary force: {}".format(ilf_type))

                if self.agent.bdi_intention_buffer:
                    temp_intentions = deque(self.agent.bdi_intention_buffer)
                    for trigger, goal_type, term, intention in temp_intentions:
                        self.agent.bdi_agent.call(trigger, goal_type, term, intention)
                        self.agent.bdi_agent.step()
                        self.agent.bdi_intention_buffer.popleft()
                else:
                    self.agent.bdi_agent.step()
            else:
                await asyncio.sleep(0.1)

        async def handle_message_with_custom_ilf_type(self, message: Message):
            pass

        def add_achievement_goal(self, functor: str, *args, intention=asp.runtime.Intention(), source=""):

            goal_type = asp.GoalType.achievement
            trigger = asp.Trigger.addition
            args2 = tuple(map(prepare_datatypes_for_asl, args))
            literal = get_literal_from_functor_and_arguments(functor, args, source=source)

            self.agent.bdi_intention_buffer.append((trigger, goal_type, literal, intention))


def parse_literal(msg):
    functor = msg.split("(")[0]
    if "(" in msg:
        args = msg.split("(")[1]
        args = args.split(")")[0]
        args = literal_eval(args)

        def recursion(arg):
            if isinstance(arg, list):
                return tuple(recursion(i) for i in arg)
            return arg

        new_args = (recursion(args),)

    else:
        new_args = ''
    return functor, new_args


# TODO rename in something more meaningful when I understand the scope of the method
def prepare_datatypes_for_asl(arguments):
    def prepare_single(argument):
        if type(argument) == str:
            return asp.Literal(argument)
        else:
            return argument
    return tuple(map(prepare_single, arguments))



def transform_message_to_literal(message: Message):
    functor, arguments = parse_literal(message.body)
    return get_literal_from_functor_and_arguments(functor, arguments, source=message.sender)


def get_literal_from_functor_and_arguments(functor, arguments, intention=asp.runtime.Intention(), source=""):
    print(arguments)
    print(prepare_datatypes_for_asl(arguments))
    literal = asp.Literal(functor, arguments)
    literal = asp.freeze(literal, intention.scope, {})
    if source:
        literal = literal.with_annotation(asp.Literal("source", (asp.Literal(str(source)),)))
    return literal



