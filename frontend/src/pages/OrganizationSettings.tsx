import { NavLink, Outlet } from 'react-router-dom'

const settingsNavItems = [
  { label: 'Users', path: '/admin-settings/users' },
  { label: 'Pricing', path: '/admin-settings/pricing' },
  { label: 'Audit Log', path: '/admin-settings/audit-log' },
]

export function OrganizationSettings() {
  return (
    <div>
      <div className="border-b border-gray-200 bg-white px-4 py-4 sm:px-6 lg:px-8">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-gray-950">Organization Settings</h1>
            <p className="mt-1 text-sm text-gray-500">Manage organization-wide users, pricing and audit history.</p>
          </div>
          <nav aria-label="Organization settings" className="flex gap-2 overflow-x-auto">
            {settingsNavItems.map(item => (
              <NavLink
                key={item.path}
                to={item.path}
                className={({ isActive }) =>
                  [
                    'flex min-h-10 items-center whitespace-nowrap rounded-md border px-3 text-sm font-medium transition',
                    isActive
                      ? 'border-blue-200 bg-blue-50 text-blue-700'
                      : 'border-gray-200 text-gray-600 hover:bg-gray-100 hover:text-gray-950',
                  ].join(' ')
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </div>
      <Outlet />
    </div>
  )
}
