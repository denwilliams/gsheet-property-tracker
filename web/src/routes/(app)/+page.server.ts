import type { Actions, PageServerLoad } from './$types';
import { fail } from '@sveltejs/kit';
import sql from '$lib/server/db';
import { parseAndAddListing } from '$lib/server/listings';

export const load: PageServerLoad = async () => {
    const properties = await sql`
        SELECT p.*,
            EXISTS(
                SELECT 1 FROM changes c
                WHERE c.property_id = p.id
                AND c.detected_at > NOW() - INTERVAL '48 hours'
            ) as has_recent_changes,
            (SELECT MAX(c.detected_at) FROM changes c WHERE c.property_id = p.id)
                as last_change_at,
            (SELECT pi.filename FROM property_images pi
                WHERE pi.property_id = p.id
                ORDER BY pi.display_order LIMIT 1)
                as hero_image
        FROM properties p
        ORDER BY p.updated_at DESC
    `;

    const areas = await sql`
        SELECT DISTINCT area FROM properties WHERE area IS NOT NULL AND area != '' ORDER BY area
    `;

    return {
        properties: properties.map(p => ({
            ...p,
            last_checked: p.last_checked?.toISOString() ?? null,
            last_change_at: p.last_change_at?.toISOString() ?? null,
            created_at: undefined,
            updated_at: undefined,
        })),
        areas: areas.map((a: any) => a.area),
    };
};

export const actions: Actions = {
    addListing: async ({ request }) => {
        const formData = await request.formData();
        const url = (formData.get('url') as string)?.trim();

        if (!url) {
            return fail(400, { addError: 'Please enter a URL' });
        }

        try {
            new URL(url);
        } catch {
            return fail(400, { addError: 'Invalid URL' });
        }

        try {
            const address = await parseAndAddListing(url);
            return { addSuccess: address };
        } catch (e: any) {
            return fail(400, { addError: e.message ?? 'Failed to add listing' });
        }
    },
};
