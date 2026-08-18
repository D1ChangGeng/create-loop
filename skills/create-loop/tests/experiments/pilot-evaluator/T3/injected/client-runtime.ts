export const sharedClient = {
  async get(key) { return globalThis.cacheService.get(key); },
  async set(key, value) { return globalThis.cacheService.set(key, value); },
};
