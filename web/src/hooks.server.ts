import type { Handle } from '@sveltejs/kit';
import { getSession } from '$lib/server/auth';

export const handle: Handle = async ({ event, resolve }) => {
    const sessionToken = event.cookies.get('session');
    if (sessionToken) {
        event.locals.user = await getSession(sessionToken);
    } else {
        event.locals.user = null;
    }
    return resolve(event);
};
