import { escapeHtml } from './map.js';

export function getMemberJitter(memberId) {
    let hash = 0;
    for (let i = 0; i < memberId.length; i += 1) {
        hash = ((hash << 5) - hash) + memberId.charCodeAt(i);
        hash |= 0;
    }
    const latOffset = ((hash % 7) - 3) * 0.00004;
    const lngOffset = (((Math.floor(hash / 7)) % 7) - 3) * 0.00004;
    return [latOffset, lngOffset];
}

export function renderConvoyMembersUI({
    members,
    convoyMemberId,
    convoyMembersUl,
    convoyMarkers,
    convoyLayer,
}) {
    convoyMembersUl.innerHTML = '';
    const activeMemberIds = new Set();

    members.forEach((member) => {
        const isMe = member.member_id === convoyMemberId;
        const name = member.name || 'Member';
        const label = isMe ? `${name} (You)` : name;

        const item = document.createElement('li');
        if (member.lat == null || member.lng == null) {
            item.textContent = `${label}: waiting for location...`;
        } else {
            const baseLat = Number(member.lat);
            const baseLng = Number(member.lng);
            const [latOffset, lngOffset] = getMemberJitter(member.member_id);
            const markerLatLng = isMe ? [baseLat, baseLng] : [baseLat + latOffset, baseLng + lngOffset];

            item.textContent = `${label}: ${baseLat.toFixed(5)}, ${baseLng.toFixed(5)}`;

            let marker = convoyMarkers.get(member.member_id);
            if (!marker) {
                marker = L.circleMarker(markerLatLng, {
                    radius: isMe ? 10 : 8,
                    color: isMe ? '#1d4ed8' : '#9a3412',
                    fillColor: isMe ? '#2563eb' : '#f97316',
                    fillOpacity: 0.95,
                    weight: 2,
                }).addTo(convoyLayer);
                convoyMarkers.set(member.member_id, marker);
            } else {
                marker.setLatLng(markerLatLng);
                marker.setStyle({
                    radius: isMe ? 10 : 8,
                    color: isMe ? '#1d4ed8' : '#9a3412',
                    fillColor: isMe ? '#2563eb' : '#f97316',
                    fillOpacity: 0.95,
                    weight: 2,
                });
            }

            const safeLabel = escapeHtml(label);
            marker.bindPopup(`<b>${safeLabel}</b><br>${baseLat.toFixed(5)}, ${baseLng.toFixed(5)}`);
            marker.bindTooltip(safeLabel, {
                permanent: true,
                direction: 'top',
                offset: [0, -12],
                className: 'convoy-label',
            });
            marker.bringToFront();
            activeMemberIds.add(member.member_id);
        }
        convoyMembersUl.appendChild(item);
    });

    for (const [memberId, marker] of convoyMarkers.entries()) {
        if (!activeMemberIds.has(memberId)) {
            convoyLayer.removeLayer(marker);
            convoyMarkers.delete(memberId);
        }
    }
}
