const base = 'http://127.0.0.1:8000';

async function fetchMessage(message) {
  const res = await fetch(base + `/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query: message })  
  });
  if (!res.ok) {
    return Promise.reject({ status: res.status, data: await res.json() });
  }
  const data =  res.json();
  return data;
}

export default {
  fetchMessage
};