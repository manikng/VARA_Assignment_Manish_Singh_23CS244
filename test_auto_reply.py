from conversation_handlers import ConversationState, respond, ConversationStore

store = ConversationStore()
state = store.get_or_create('test_conv', 'm_001', None)
state.trigger_kind = 'research_digest'
state.trigger_payload = {}

# Turn 1: Bot initiates (not tracked in state.turns)
# Turn 2: Merchant sends auto-reply
state.turns.append({'from': 'vera', 'msg': 'Initial message'})
res = respond(state, 'Thank you for contacting Dr. Meera! Our team will respond shortly.', 2)
print('Turn 2 (first auto-reply):', res)

# Turn 3: Merchant sends same auto-reply again
state.turns.append({'from': 'merchant', 'msg': 'Thank you for contacting Dr. Meera! Our team will respond shortly.'})
res = respond(state, 'Thank you for contacting Dr. Meera! Our team will respond shortly.', 3)
print('Turn 3 (second auto-reply):', res)

# Turn 4: Merchant sends same auto-reply third time
state.turns.append({'from': 'merchant', 'msg': 'Thank you for contacting Dr. Meera! Our team will respond shortly.'})
res = respond(state, 'Thank you for contacting Dr. Meera! Our team will respond shortly.', 4)
print('Turn 4 (third auto-reply):', res)