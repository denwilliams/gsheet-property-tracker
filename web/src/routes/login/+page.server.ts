import { fail, redirect } from '@sveltejs/kit';
import type { Actions } from './$types';
import { validateCredentials, createSession } from '$lib/server/auth';

export const actions: Actions = {
    default: async ({ request, cookies }) => {
        const data = await request.formData();
        const email = data.get('email') as string;
        const password = data.get('password') as string;

        if (!email || !password) {
            return fail(400, { error: 'Email and password required', email });
        }

        const valid = await validateCredentials(email, password);
        if (!valid) {
            return fail(401, { error: 'Invalid credentials', email });
        }

        const token = await createSession(email);
        cookies.set('session', token, {
            path: '/',
            httpOnly: true,
            sameSite: 'lax',
            secure: true,
            maxAge: 7 * 24 * 60 * 60,
        });

        redirect(302, '/');
    },
};
