import { redirect } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { deleteSession } from '$lib/server/auth';

export const POST: RequestHandler = async ({ cookies }) => {
    const token = cookies.get('session');
    if (token) {
        await deleteSession(token);
        cookies.delete('session', { path: '/' });
    }
    redirect(302, '/login');
};
