import { api } from '@/shared/api';

/** 공지 등록 (operationId: createNotice) */
export async function createNotice(title: string): Promise<number> {
  return api.post('/api/v1/notices', { title });
}

/**
 * 공지 목록 조회 (operationId: searchNotices)
 */
export const searchNotices = async (page: number) => api.get('/api/v1/notices', { page });
