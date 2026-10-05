import { Shield } from 'lucide-react'
import { useAuth } from '@/auth/AuthProvider'

export default function OrganizationSelector() {
  const { memberships, userInfo, selectOrganization, switchOrganization, selectedOrgId, logout } = useAuth()

  const current = memberships.find((m) => m.organization_id === selectedOrgId)

  return (
    <div className="flex items-center justify-center min-h-screen bg-background-primary">
      <div className="w-full max-w-sm rounded-lg border border-border bg-background-secondary p-8">
        <div className="flex justify-center mb-4">
          <Shield className="w-8 h-8 text-accent-sovereign" />
        </div>
        <h1 className="text-lg font-bold text-text-primary text-center mb-1">SOVEREIGN AI</h1>
        <p className="text-xs text-text-secondary text-center mb-4">
          {userInfo?.display_name ?? 'User'} — select an organization
        </p>

        <div className="space-y-2 mb-4">
          {memberships.map((m) => (
            <button
              key={m.organization_id}
              type="button"
              onClick={() => {
                if (current?.organization_id === m.organization_id) return
                if (selectedOrgId) {
                  switchOrganization(m.organization_id)
                } else {
                  selectOrganization(m.organization_id)
                }
              }}
              className={`w-full rounded-md border px-3 py-2 text-left text-sm transition-colors ${
                current?.organization_id === m.organization_id
                  ? 'border-accent-primary bg-accent-primary/10 text-accent-primary'
                  : 'border-border hover:bg-background-tertiary text-text-primary'
              }`}
            >
              <p className="font-medium">{m.organization_name}</p>
              <p className="text-[10px] text-text-secondary capitalize">{m.role}</p>
            </button>
          ))}
        </div>

        <button
          type="button"
          onClick={logout}
          className="w-full rounded-md border border-border px-3 py-2 text-xs text-text-secondary hover:bg-background-tertiary"
        >
          Sign out
        </button>
      </div>
    </div>
  )
}
