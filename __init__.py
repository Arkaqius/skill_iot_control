# Copyright 2019 Mycroft AI Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

# TODO Exceptions should be custom types

from collections import defaultdict, namedtuple
from enum import Enum
from typing import DefaultDict, Dict, List
from uuid import uuid4

from adapt.intent import IntentBuilder
from mycroft import MycroftSkill
from mycroft.messagebus.message import Message
from mycroft.skills.common_iot_skill import (IOT_REQUEST_ID, Action, Attribute,Location,
                                             IoTRequest, State, Thing,LightTemperature,
                                             _BusKeys)
from mycroft.util.log import LOG
from mycroft.util.parse import extract_number

_QUERY_ACTIONS = [Action.BINARY_QUERY.name, Action.INFORMATION_QUERY.name]
_NON_QUERY_ACTIONS = [action.name for action in Action if action.name not in _QUERY_ACTIONS]
_THINGS = [thing.name for thing in Thing]
_ATTRIBUTES = [attribute.name for attribute in Attribute]
_LOCATIONS =  [location.name for location in Location]
_STATES = [state.name for state in State]
_LIGHT_TEMPERATURE = [LightTemperature.name for LightTemperature in LightTemperature]


class IoTRequestStatus(Enum):
    POLLING = 0
    RUNNING = 1

class LightTemperatureNumValues(Enum):
    WARM = 470
    COLD = 200

SpeechRequest = namedtuple('SpeechRequest', ["utterance", "args", "kwargs"])

class TrackedIoTRequest():

    def __init__(
            self,
            id: str,
            status: IoTRequestStatus = IoTRequestStatus.POLLING,
    ):
        self.id = id
        self.status = status
        self.candidates = []
        self.speech_requests: DefaultDict[str, List[SpeechRequest]] = defaultdict(list)

class SkillIoTControl(MycroftSkill):

    def __init__(self):
        MycroftSkill.__init__(self)
        self._current_requests: Dict[str, TrackedIoTRequest] = dict()
        self._normalized_to_orignal_word_map: Dict[str, str] = dict()

    @property
    def response_timeout(self):
        return self.settings.get('response_timeout')

    def _handle_speak(self, message: Message):
        iot_request_id = message.data.get(IOT_REQUEST_ID)

        skill_id = message.data.get("skill_id")

        utterance = message.data.get("speak")
        args = message.data.get("speak_args")
        kwargs = message.data.get("speak_kwargs")

        speech_request = SpeechRequest(utterance, args, kwargs)

        if iot_request_id not in self._current_requests:
            LOG.warning("Dropping speech request from {skill_id} for"
                        " {iot_request_id} because we are not currently"
                        " tracking that iot request. SpeechRequest was"
                        " {speech_request}".format(
                skill_id=skill_id,
                iot_request_id=iot_request_id,
                speech_request=speech_request
            ))

        self._current_requests[iot_request_id].speech_requests[skill_id].append(speech_request)
        LOG.info(self._current_requests[iot_request_id].speech_requests[skill_id])

    def initialize(self):
        #Special words initializaion
        self._SPECIAL_WORDS = ['turn', 'to', 'percent', 'of', 'what','is','on','off', 'level'] #TODO Ugly implementation, should be file or smth
        self._VALUE_KEYWORDS = {'half' : 0.5, "quarter" : 0.25}

        self.add_event(_BusKeys.RESPONSE, self._handle_response)
        self.add_event(_BusKeys.REGISTER, self._register_words)
        self.add_event(_BusKeys.SPEAK, self._handle_speak)
        self.bus.emit(Message(_BusKeys.CALL_FOR_REGISTRATION, {}))

        intent = (IntentBuilder('IoTRequestWithEntityOrThingAndLocation')
                    .one_of('ENTITY', *_THINGS)
                    .one_of(*_NON_QUERY_ACTIONS)
                    .one_of(*_LOCATIONS)
                    .optionally('SCENE')
                    .optionally('TO')
                    .build())
        self.register_intent(intent, self._handle_iot_request)

        intent = (IntentBuilder('IoTRequestWithEntityOrThingWithoutLocation')
                    .one_of('ENTITY', *_THINGS)
                    .one_of(*_NON_QUERY_ACTIONS)
                    .optionally('SCENE')
                    .optionally('TO')
                    .build())
        self.register_intent(intent, self._handle_iot_request)

        intent = (IntentBuilder('IoTRequestWithEntityOrThingAndAttributeWithLocation')
                    .one_of('ENTITY', *_THINGS)
                    .one_of(*_NON_QUERY_ACTIONS)
                    .one_of(*_ATTRIBUTES)
                    .one_of(*_LOCATIONS)
                    .optionally('SCENE')
                    .optionally('TO')
                    .build())
        self.register_intent(intent, self._handle_iot_request)

        intent = (IntentBuilder('IoTRequestWithEntityOrThingAndAttributeWithOutLocation')
                    .one_of('ENTITY', *_THINGS)
                    .one_of(*_NON_QUERY_ACTIONS)
                    .one_of(*_ATTRIBUTES)
                    .optionally('SCENE')
                    .optionally('TO')
                    .build())
        self.register_intent(intent, self._handle_iot_request)

        intent = (IntentBuilder('IoTRequestScene')
                  .require('SCENE')
                  .one_of(*_NON_QUERY_ACTIONS)
                  .build())
        self.register_intent(intent, self._handle_iot_request)

        intent = (IntentBuilder('IoTRequestStateQueryWithLocation')
                    .one_of(*_QUERY_ACTIONS)
                    .one_of(*_THINGS, 'ENTITY')
                    .one_of(*_STATES, *_ATTRIBUTES)
                    .one_of(*_LOCATIONS)
                    .build())
        self.register_intent(intent, self._handle_iot_request)

        intent = (IntentBuilder('IoTRequestStateQueryWithoutLocation')
                    .one_of(*_QUERY_ACTIONS)
                    .one_of(*_THINGS, 'ENTITY')
                    .one_of(*_STATES, *_ATTRIBUTES)
                    .build())
        self.register_intent(intent, self._handle_iot_request)

        '''
        intent = (IntentBuilder('IoTRequestWithEntityOrThingAndAttribute')
                    .one_of('ENTITY', *_THINGS)
                    .one_of(*_NON_QUERY_ACTIONS)
                    .one_of(*_ATTRIBUTES)
                    .one_of(*_LOCATIONS)
                    .one_of(*_LIGHT_TEMPERATURE)
                    .optionally('SCENE')
                    .optionally('TO')
                    .build())
        self.register_intent(intent, self._handle_iot_request)
        '''

        '''
        intent = (IntentBuilder('IoTRequestWithEntityAndThingAndAttribute')
                    .require('ENTITY')
                    .one_of(*_THINGS)
                    .one_of(*_NON_QUERY_ACTIONS)
                    .one_of(*_ATTRIBUTES)
                    .one_of(*_LOCATIONS)
                    .optionally('SCENE')
                    .optionally('TO')
                    .build())
        self.register_intent(intent, self._handle_iot_request)
        '''

        '''
        intent = (IntentBuilder('IoTRequestWithEntityAndThing')
                    .require('ENTITY')
                    .one_of(*_THINGS)
                    .one_of(*_NON_QUERY_ACTIONS)
                    .one_of(*_LOCATIONS)
                    .optionally('SCENE')
                    .optionally('TO')
                    .build())
        self.register_intent(intent, self._handle_iot_request)
        '''
    def stop(self):
        pass

    def _handle_response(self, message: Message):
        id = message.data.get(IOT_REQUEST_ID)
        if not id:
            LOG.error("No id found in message data. Cannot handle this iot request!")
            return
        if id not in self._current_requests:
            LOG.warning("Request is not being tracked. This skill may have responded too late.")
            return
        if self._current_requests[id].status != IoTRequestStatus.POLLING:
            LOG.warning("Skill responded too late. Request is no longer POLLING.")
            return
        self._current_requests[id].candidates.append(message)

    def _register_words(self, message: Message):
        type = message.data["type"]
        words = message.data["words"]

        for word in words:
            self.register_vocabulary(word, type)
            normalized = _normalize_custom_word(word)
            if normalized != word:
                self._normalized_to_orignal_word_map[normalized] = word
                self.register_vocabulary(normalized, type)

    def _run(self, message: Message):
        id = message.data.get(IOT_REQUEST_ID)
        request = self._current_requests.get(id)

        if request is None:
            raise Exception("This id is not being tracked!")

        request.status = IoTRequestStatus.RUNNING
        candidates = request.candidates

        if not candidates:
            self.speak_dialog('no.skills.can.handle')
        else:
            winners = self._pick_winners(candidates)
            for winner in winners:
                self.bus.emit(Message(
                    _BusKeys.RUN + winner.data["skill_id"], winner.data))

            self.schedule_event(self._speak_or_acknowledge,
                                self.response_timeout,
                                data={IOT_REQUEST_ID: id},
                                name="SpeakOrAcknowledge")

    def _speak_or_acknowledge(self, message: Message):
        id = message.data.get(IOT_REQUEST_ID)
        request = self._current_requests.get(id)

        if not request.speech_requests:
            self.acknowledge()
        else:
            skill_id, requests = request.speech_requests.popitem()
            for utterance, args, kwargs in requests:
                self.speak(utterance, *args, **kwargs)
            if request.speech_requests:
                LOG.info("Ignoring speech requests from {speech_requests}. "
                         "{skill_id} was the winner."
                         .format(
                             speech_requests=request.speech_requests,
                             skill_id=skill_id))

    def _delete_request(self, message: Message):
        id = message.data.get(IOT_REQUEST_ID)
        LOG.info("Delete request {id}".format(id=id))
        try:
            del(self._current_requests[id])
        except KeyError:
            pass

    def _pick_winners(self, candidates: List[Message]):
        # TODO - make this actually pick winners
        return candidates

    def _get_enum_from_data(self, enum_class, data: dict):
        for e in enum_class:
            if e.name in data:
                return e
        return None

    def _get_value_from_keywords(self,utterence):
        for keyword in self.VALUE_KEYWORDS.keys():
            if str.lower(keyword.name) in str.lower(utterence):
                return self.VALUE_KEYWORDS[keyword]

    def _transformLightTemperatureToVal(self,enum_val : LightTemperature):
        if enum_val == LightTemperature.WARM:
            return 470
        elif enum_val == LightTemperature.COLD:
            return 200

    def _remove_keywords(self,action,thing,attribute,location,state,entity,scene,data):
        found_keywords = []
        if action is not None:
            found_keywords.append(data[action.name].lower())
            found_keywords.append(action.name.lower())
        if thing is not None:
            found_keywords.append(data[thing.name].lower())
        if attribute is not None:
            found_keywords.append(data[attribute.name].lower())
        if location is not None:
            found_keywords.extend(data[location.name].lower().split(' '))
        if state is not None:
            found_keywords.append(data[state.name].lower())
        if entity is not None:
            found_keywords.append(data[entity.name].lower())
        if scene is not None:
            found_keywords.append(data[scene.name].lower())
        return found_keywords
        
    def _get_all_descriptions(self,found_keywords,utterence): 
        #Get all keywords from utterence
        description = [x for x in utterence.split() if x not in found_keywords]
        #Filtered out special words (ie. turn)
        description = [x for x in description if x not in self._SPECIAL_WORDS]
        #Filter out value keywords
        description = [x for x in description if x not in self._VALUE_KEYWORDS]

        return description

    def _get_value(self,action,thing,attribute,data,utterence):
        value = None

        #Value parsing from request, it depends on others values
        if (action == Action.SET or action == Action.ADJUST) and 'TO' in data:
            #Check for percent
            if 'percent' in utterence:
                value = extract_number(utterence)/100
            else:    
                value = extract_number(utterence)
            # extract_number may return False:
            if None == value:   
                value = self._get_value_from_keywords(utterence)
        return value

    def _handle_iot_request(self, message: Message):

        #Generate uuid for that request!
        id = str(uuid4())
        message.data[IOT_REQUEST_ID] = id
        self._current_requests[id] = TrackedIoTRequest(id)

        #Parse request to keywords
        data = self._clean_power_request(message.data)
        action = self._get_enum_from_data(Action, data)
        thing = self._get_enum_from_data(Thing, data)
        attribute = self._get_enum_from_data(Attribute, data)
        location = self._get_enum_from_data(Location,data)
        state = self._get_enum_from_data(State, data)
        entity = data.get('ENTITY')
        scene = data.get('SCENE')
        value = None

        #Create list of all found keywords
        found_keywords = self._remove_keywords( action,thing,attribute,location,state,entity,scene,data)

        #Take out all keywords and generate description (Everything what is NOT keywords)                 
        description = self._get_all_descriptions(found_keywords,message.data['utterance'])

        #Get value from request
        value = self._get_value(action,thing,attribute,data,message.data['utterance'])
        #Take out all value keywords
        if value:
            description = [x for x in description if not x.isdigit()]

        """ #Dodgy processing
        if value == None:
            value = self._get_value_from_keywords(LightTemperature,message.data['utterance'])

        '''
        TODO Transform keywords to numerical values
        '''
        #Light Temperature
        if(entity is not None):
            if(attribute == Attribute.TEMPERATURE and 'light' in entity):
                value = self._transformLightTemperatureToVal(value) """

        original_entity = (self._normalized_to_orignal_word_map.get(entity)
                           if entity else None)
        original_scene = (self._normalized_to_orignal_word_map.get(scene)
                          if scene else None)

        self._trigger_iot_request(
            data,
            action,
            thing,
            attribute,
            location,
            entity,
            scene,
            value,
            state,
            description
        )

        if original_entity or original_scene:
            self._trigger_iot_request(data, action, thing, attribute,location,
                                      original_entity or entity,
                                      original_scene or scene,
                                      state,description)

        self.schedule_event(self._delete_request,
                            10 * self.response_timeout,
                            data={IOT_REQUEST_ID: id},
                            name="DeleteRequest")
        self.schedule_event(self._run,
                            self.response_timeout,
                            data={IOT_REQUEST_ID: id},
                            name="RunIotRequest")

    def _trigger_iot_request(self, data: dict,
                             action: Action,
                             thing: Thing=None,
                             attribute: Attribute=None,
                             location: Location=None,
                             entity: str=None,
                             scene: str=None,
                             value: int=None,
                             state: State=None,
                             description: list=None):
        LOG.info('state is {}'.format(state))
        request = IoTRequest(
            action=action,
            thing=thing,
            attribute=attribute,
            location=location,
            entity=entity,
            scene=scene,
            value=value,
            state=state,
            description = description
            
        )

        LOG.info("Looking for handlers for: {request}".format(request=request))

        data[IoTRequest.__name__] = request.to_dict()

        self.bus.emit(Message(_BusKeys.TRIGGER, data))

    def _set_context(self, thing: Thing, entity: str, data: dict):
        if thing:
            self.set_context(thing.name, data[thing.name])
        if entity:
            self.set_context('ENTITY', entity)

    def _clean_power_request(self, data: dict) -> dict:
        """
        Clean requests that include a toggle word and a definitive value.

        Requests like "toggle the lights off" should only send "off"
        through as the action.

        Args:
            data: dict

        Returns:
            dict

        """
        if 'TOGGLE' in data and ('ON' in data or 'OFF' in data):
            del(data['TOGGLE'])
        return data

def _normalize_custom_word(word: str, to_space: str = '_-') -> str:
    word = word.lower()
    letters = list(word)
    for index, letter in enumerate(letters):
        if letter in to_space:
            letters[index] = ' '
    return ''.join(letters)

def create_skill():
    return SkillIoTControl()
