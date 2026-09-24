import httpx

def post(task, asset_tag=None, use_rag=False):
    with httpx.Client(timeout=60.0) as c:
        r = c.post('http://127.0.0.1:8000/api/general/run', json={
            'task': task,
            'asset_tag': asset_tag,
            'use_rag': use_rag,
        })
    return r.status_code, r.json()

queries = [
    ('Hey, what can you do?', None, False),
    ('Explain what a P&ID is in simple terms.', None, False),
    ('What is the difference between preventive and corrective maintenance?', None, False),
    ('Give me information about the inspection report for R-1001.', 'R-1001', True),
    ('Compare the inspection findings with the vendor recommendations for R-1001.', 'R-1001', True),
    ('Analyze R-1001 operating data and inspection findings, compare them with the equipment manual, maintenance SOP and vendor recommendations, determine the required corrective action, and prepare a maintenance approval note.', 'R-1001', False),
]

for i, (q, tag, rag) in enumerate(queries, 1):
    status, data = post(q, tag, rag)
    answer = str(data.get('answer', ''))[:120]
    print(f'{i}. {q[:60]}...')
    print(f'   HTTP: {status}')
    print(f"   Status: {data['status']}")
    print(f"   Actual execution: {data['actual_model_execution']}")
    print(f"   RAG: {data['rag_used']}")
    print(f'   Answer: {answer}')
    print()
