const BASE = "https://docex-production-e070.up.railway.app";

export async function fetchWithAuth(endpoint: string, options: RequestInit = {}) {
  const response = await fetch(`${BASE}${endpoint}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });

  if (!response.ok) {
    const text = await response.text();
    try {
      const json = JSON.parse(text);
      throw new Error(json.detail || `Request failed: ${response.status}`);
    } catch {
      throw new Error(text || `Request failed: ${response.status}`);
    }
  }

  return response.json();
}

// Rulebooks API
export async function getRulebooks() {
  return fetchWithAuth("/api/rulebooks");
}

export async function createRulebook(data: any) {
  return fetchWithAuth("/api/rulebooks", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function getRulebook(id: string) {
  return fetchWithAuth(`/api/rulebooks/${id}`);
}

// Compliance API
export async function checkCompliance(data: any) {
  return fetchWithAuth("/api/compliance/check", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function getComplianceChecks() {
  return fetchWithAuth("/api/compliance/checks");
}

// Bank Verification API
export async function verifyBank(data: any) {
  return fetchWithAuth("/api/verify/bank", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

// Attendance Payment API
export async function createAttendancePayment(data: any) {
  return fetchWithAuth("/api/attendance-payment", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

// Knowledge API
export async function getKnowledgeBase() {
  return fetchWithAuth("/api/knowledge");
}

export async function searchKnowledge(query: string) {
  return fetchWithAuth(`/api/knowledge/search?q=${encodeURIComponent(query)}`);
}

// Templates API
export async function getTemplates() {
  return fetchWithAuth("/api/templates");
}

export async function createTemplate(data: any) {
  return fetchWithAuth("/api/templates", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

// Extract API
export async function extractContent(data: any) {
  return fetchWithAuth("/api/extract", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

// Rate Cards API
export async function getRateCards() {
  return fetchWithAuth("/api/rate-cards");
}
