// Remembers the current job and which exceptions were resolved. Falls back to memory if storage is blocked.
const JOB_KEY = "crushdata:jobId";
let memoryJobId: string | null = null;
const memoryResolved = new Map<string, string[]>();

export function getJobId(): string | null {
  try {
    return localStorage.getItem(JOB_KEY) ?? memoryJobId;
  } catch {
    return memoryJobId;
  }
}

export function setJobId(id: string) {
  memoryJobId = id;
  try {
    localStorage.setItem(JOB_KEY, id);
  } catch {
    /* storage unavailable: memory copy is enough for this session */
  }
}

export function getResolved(jobId: string): string[] {
  try {
    const raw = localStorage.getItem(`crushdata:resolved:${jobId}`);
    return raw ? (JSON.parse(raw) as string[]) : (memoryResolved.get(jobId) ?? []);
  } catch {
    return memoryResolved.get(jobId) ?? [];
  }
}

export function setResolved(jobId: string, domains: string[]) {
  memoryResolved.set(jobId, domains);
  try {
    localStorage.setItem(`crushdata:resolved:${jobId}`, JSON.stringify(domains));
  } catch {
    /* ignore */
  }
}
