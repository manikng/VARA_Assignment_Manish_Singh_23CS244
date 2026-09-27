from conversation_handlers import ConversationState, respond, ConversationStore

store = ConversationStore()

# Simulate tick creating a conversation with trigger context
# (This is what bot.py now does in the tick endpoint)
conv_id = 'conv_m_001_trg_001'
merchant_id = 'm_001_drmeera_dentist_delhi'
customer_id = None

# Get/create conversation state (this is what tick does)
conv_state = store.get_or_create(conv_id, merchant_id, customer_id)
conv_state.trigger_kind = 'research_digest'
conv_state.trigger_payload = {'top_item_id': 'd_2026W17_jida_fluoride'}

# Now simulate a reply coming in
# bot.py appends the message to turns before calling respond
conv_state.turns.append({'from': 'vera', 'msg': 'Dr. Meera, JIDA Oct issue...'})
res = respond(conv_state, 'Btw can you also help me with my GST filing this month?', 2)

print('Response:', res)
print()
print('Body:', res['body'])
print('CTA:', res['cta'])
print('Rationale:', res['rationale'])