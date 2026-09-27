from conversation_handlers import ConversationState, respond, ConversationStore

store = ConversationStore()

# Test 1: research_digest trigger with GST question
state = store.get_or_create('test_conv1', 'm_001', None)
state.trigger_kind = 'research_digest'
state.trigger_payload = {}
state.turns.append({'from': 'vera', 'msg': 'Initial message'})
res = respond(state, 'Btw can you also help me with my GST filing this month?', 2)
print('Test 1 - research_digest + GST:', res['body'])

# Test 2: recall_due trigger with GST question
state2 = store.get_or_create('test_conv2', 'm_001', 'c_001')
state2.trigger_kind = 'recall_due'
state2.trigger_payload = {}
state2.turns.append({'from': 'vera', 'msg': 'Initial message'})
res2 = respond(state2, 'Can you help with GST filing?', 2)
print('Test 2 - recall_due + GST:', res2['body'])

# Test 3: perf_dip trigger with GST question
state3 = store.get_or_create('test_conv3', 'm_001', None)
state3.trigger_kind = 'perf_dip'
state3.trigger_payload = {}
state3.turns.append({'from': 'vera', 'msg': 'Initial message'})
res3 = respond(state3, 'Help with tax filing please', 2)
print('Test 3 - perf_dip + tax:', res3['body'])

# Test 4: Generic trigger with GST question
state4 = store.get_or_create('test_conv4', 'm_001', None)
state4.trigger_kind = 'unknown_trigger'
state4.trigger_payload = {}
state4.turns.append({'from': 'vera', 'msg': 'Initial message'})
res4 = respond(state4, 'What about income tax?', 2)
print('Test 4 - unknown + tax:', res4['body'])

# Test 5: commitment detection
state5 = store.get_or_create('test_conv5', 'm_001', None)
state5.trigger_kind = 'research_digest'
state5.trigger_payload = {}
state5.turns.append({'from': 'vera', 'msg': 'Initial message'})
res5 = respond(state5, 'Ok let\'s do it', 2)
print('Test 5 - commitment:', res5['body'])

# Test 6: hostile detection
state6 = store.get_or_create('test_conv6', 'm_001', None)
state6.trigger_kind = 'research_digest'
state6.trigger_payload = {}
state6.turns.append({'from': 'vera', 'msg': 'Initial message'})
res6 = respond(state6, 'Stop messaging me', 2)
print('Test 6 - hostile:', res6)