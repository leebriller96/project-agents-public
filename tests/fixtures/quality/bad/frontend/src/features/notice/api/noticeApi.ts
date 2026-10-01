import { api } from '@/shared/api';

export async function createNotice(title: string): Promise<number> {
  console.log('등록', title);
  return api.post('/api/v1/notices', { title });
}
